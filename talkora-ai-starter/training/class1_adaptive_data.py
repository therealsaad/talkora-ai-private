"""Generate original, synthetic Class 1 adaptive-teaching hints for review.

Version 2 fixes generic answers and stratifies the held-out split across words,
languages, and scaffold modes. Nothing is fine-tuned or deployed by this file.

Run from talkora-ai-starter:
    python -m training.class1_adaptive_data --out datasets/training/class1-adaptive-v2
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from server.class1_adaptive import (
    APPROVED_WORDS,
    CONTEXT_WORDS,
    CURRICULUM,
    MODES,
    SYSTEM_INSTRUCTIONS,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "datasets" / "training" / "class1-adaptive-v2"
LANGUAGES = ("en", "hi", "mr")
TARGET_WORDS = ("am", "an", "at", "in", "is", "it", "on", "up", "school", "walk")
SCENARIOS = (
    ("different", "MODEL"),
    ("unsure", "GUIDE"),
    ("heard", "PRACTISE"),
    ("sentence", "EXTEND"),
)

# Original, short, bilingual teacher utterances. All model/guide samples explicitly
# demonstrate the requested word. Heard/PRACTISE samples do not say "try again".
# Teacher review of Hindi/Marathi phrasing is REQUIRED before any serious training.
HINTS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "MODEL": ("Listen: {word}. Now say {word} with me.",
                  "Our little word is {word}. Say {word} slowly."),
        "GUIDE": ("It's okay. Listen to {word}. Try saying {word}.",
                  "I'll help: {word}. Say {word} with me."),
        "PRACTISE": ("Nice effort with {word}! Let's use it in a sentence.",
                     "Good effort! Let's use {word} in school talk."),
        "EXTEND": ("Nice try using {word}! Let's make another short sentence.",
                   "Let's use {word} in another little school sentence."),
    },
    "hi": {
        "MODEL": ("सुनो: {word}। अब मेरे साथ {word} बोलो।",
                  "छोटा शब्द है {word}। धीरे से {word} बोलो।"),
        "GUIDE": ("कोई बात नहीं। सुनो {word}। अब {word} बोलो।",
                  "मैं बोलती हूँ: {word}। तुम भी {word} बोलो।"),
        "PRACTISE": ("अच्छी कोशिश! अब {word} से छोटा वाक्य बनाओ।",
                     "बढ़िया कोशिश! {word} को छोटे वाक्य में बोलो।"),
        "EXTEND": ("अच्छी कोशिश! {word} वाला एक और छोटा वाक्य बोलो।",
                   "अब {word} का इस्तेमाल करके छोटा वाक्य बनाओ।"),
    },
    "mr": {
        "MODEL": ("ऐक: {word}. आता माझ्यासोबत {word} म्हण.",
                  "छोटा शब्द {word}. हळूच {word} म्हण."),
        "GUIDE": ("काळजी करू नकोस. ऐक {word}. आता {word} म्हण.",
                  "मी म्हणते: {word}. तूही {word} म्हण."),
        "PRACTISE": ("छान प्रयत्न! आता {word} वापरून छोटे वाक्य म्हण.",
                     "मस्त प्रयत्न! {word} वापरून वाक्य म्हण."),
        "EXTEND": ("छान! {word} वापरून आणखी एक छोटे वाक्य म्हण.",
                   "आता {word} वापरून शाळेबद्दल छोटे वाक्य म्हण."),
    },
}


def _context(word: str, language: str, mode: str, scenario: str, variant: int) -> dict[str, Any]:
    heard = scenario in ("heard", "sentence")
    different = "up" if word != "up" else "at"
    sentence = (
        "I walk to school." if word == "walk" else
        "I am at school." if word == "school" else
        "Look at me." if word == "at" else
        "I am Sam." if word == "am" else
        f"I can say {word}."
    )
    transcript = sentence if scenario == "sentence" else (
        word if heard else different if scenario == "different" else "I don't know"
    )
    goal = CURRICULUM["learningGoals"][2 if word in CONTEXT_WORDS else 0]
    return {
        "target": word,
        "transcript": transcript,
        "word_visible_in_transcript": heard,
        "support_language": language,
        "teacher_question": f"{'Repeat' if variant else 'Say'} the word {word}.",
        "approved_vocabulary": sorted(
            APPROVED_WORDS if word in CONTEXT_WORDS else set(CURRICULUM["foundationWords"])
        ),
        "lesson_unit": CURRICULUM["syllabus"]["unit"],
        "learning_goal": goal,
        "scaffold_mode": mode,
        "scaffold_instruction": MODES[mode],
    }


def _split_for(word_index: int, lang_index: int, scenario_index: int, variant: int) -> str:
    """Keep 192/24/24 while placing every approved target in each split.

    Different teacher-question variants separate validation from testing.
    This measures seen-word coaching, NOT generalization to unseen words.
    """
    holdouts = 2 if word_index < 6 else 3
    for offset in range(holdouts):
        if (lang_index == (word_index + offset) % len(LANGUAGES)
                and scenario_index == (word_index + offset) % len(SCENARIOS)
                and variant == 1):
            return "test"
        if (lang_index == (word_index + offset + 1) % len(LANGUAGES)
                and scenario_index == (word_index + offset + 2) % len(SCENARIOS)
                and variant == 0):
            return "validation"
    return "train"


def _validate_example(row: dict[str, Any]) -> None:
    payload = json.loads(row["messages"][1]["content"])
    answer = json.loads(row["messages"][2]["content"])
    assert set(answer) == {"hint"} and isinstance(answer["hint"], str)
    hint = answer["hint"]
    assert 1 <= len(hint.split()) <= 12, f"Hint is too long: {hint!r}"
    assert re.search(r"\b" + re.escape(payload["target"]) + r"\b", hint, flags=re.I), (
        f"Hint omits target {payload['target']!r}: {hint!r}"
    )
    if payload["scaffold_mode"] == "PRACTISE":
        assert "try again" not in hint.lower(), "Do not tell an engaged student to retry"
    assert row["metadata"]["synthetic"] is True
    assert row["metadata"]["reviewed"] is False


def build_examples() -> dict[str, list[dict[str, Any]]]:
    if set(TARGET_WORDS) != set(APPROVED_WORDS):
        raise ValueError("Approved Class 1 curriculum changed. Review targets before generating.")
    output: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for word_index, word in enumerate(TARGET_WORDS):
        for lang_index, language in enumerate(LANGUAGES):
            for scenario_index, (scenario, mode) in enumerate(SCENARIOS):
                for variant, template in enumerate(HINTS[language][mode]):
                    payload = _context(word, language, mode, scenario, variant)
                    hint = template.format(word=word)
                    row = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                            {"role": "assistant", "content": json.dumps({"hint": hint}, ensure_ascii=False)},
                        ],
                        "metadata": {
                            "level_id": CURRICULUM["levelId"],
                            "target": word,
                            "scenario": scenario,
                            "mode": mode,
                            "language": language,
                            "synthetic": True,
                            "reviewed": False,
                            "dataset_version": "class1-adaptive-v2",
                        },
                    }
                    _validate_example(row)
                    output[_split_for(word_index, lang_index, scenario_index, variant)].append(row)

    counts = {name: len(examples) for name, examples in output.items()}
    if counts != {"train": 192, "validation": 24, "test": 24}:
        raise ValueError(f"Unexpected split sizes: {counts}")
    if any({r["metadata"]["target"] for r in examples} != set(TARGET_WORDS)
           for examples in output.values()):
        raise ValueError("Every split must cover every approved target")
    return output


def prepare(out: Path = DEFAULT_OUT) -> dict[str, int]:
    examples = build_examples()  # Fail before writing any dataset file.
    out.mkdir(parents=True, exist_ok=True)
    for split, records in examples.items():
        with (out / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {split: len(records) for split, records in examples.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print("Synthetic Class 1 adaptive v2 examples:", prepare(args.out))
    print("HUMAN EDUCATOR REVIEW REQUIRED. Nothing was fine-tuned or deployed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
