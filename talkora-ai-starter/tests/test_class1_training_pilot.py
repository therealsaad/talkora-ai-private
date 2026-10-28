"""No GPU, model download, running server, or external curriculum required."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from training.class1_pilot import (
    FOUNDATION_WORDS, LEVEL_ID, build_examples, encode_example,
    evaluate_live, load_lesson, load_rows, prepare,
)


@pytest.fixture
def local_lesson(tmp_path):
    path = tmp_path / "class1.json"
    path.write_text(json.dumps({
        "approved_foundation_words": list(FOUNDATION_WORDS),
        "model_sentences": {"at": "Look at me."},
    }), encoding="utf-8")
    return path


def test_dataset_uses_existing_contract_and_held_out_words(local_lesson, tmp_path):
    folder = tmp_path / "datasets"
    assert prepare(local_lesson, folder) == {"train": 108, "validation": 18, "test": 18}
    splits = {part: load_rows(folder / f"{part}.jsonl")
              for part in ("train", "validation", "test")}
    words = [{row["metadata"]["target"] for row in records} for records in splits.values()]
    assert words[0].isdisjoint(words[1])
    assert words[0].isdisjoint(words[2])
    assert words[1].isdisjoint(words[2])
    assert set().union(*words) == set(FOUNDATION_WORDS)
    for records in splits.values():
        for row in records:
            assert row["metadata"]["level_id"] == LEVEL_ID
            assert [message["role"] for message in row["messages"]] == ["system", "user", "assistant"]
            assert set(json.loads(row["messages"][2]["content"])) == {"hint"}
            prompt = json.loads(row["messages"][1]["content"])
            assert set(prompt) == {"target", "transcript", "word_visible_in_transcript",
                                   "support_language", "teacher_question", "approved_vocabulary"}


def test_prepare_refuses_unapproved_word_changes(local_lesson):
    payload = json.loads(local_lesson.read_text(encoding="utf-8"))
    payload["approved_foundation_words"].append("hello")
    local_lesson.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected approved word list"):
        load_lesson(local_lesson)


class TinyTokenizer:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False,
                            enable_thinking=False):
        value = "".join(f"{part['role']}:{part['content']}|" for part in messages)
        return value + ("assistant:" if add_generation_prompt else "")

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(character) for character in text]}


def test_only_assistant_tokens_get_labels(local_lesson):
    row = build_examples(load_lesson(local_lesson))["train"][0]
    result = encode_example(TinyTokenizer(), row, 3000)
    assert len(result["input_ids"]) == len(result["labels"])
    first_supervised = next(i for i, label in enumerate(result["labels"]) if label != -100)
    assert first_supervised > 0
    assert result["labels"][first_supervised:] == result["input_ids"][first_supervised:]
    with pytest.raises(ValueError, match="exceeds max_length"):
        encode_example(TinyTokenizer(), row, 50)


def fake_success(req):
    target = req["currentQuestion"].removeprefix("Say the word ").rstrip(".")
    unknown = target == "What did you hear?"
    observed = not unknown and req["studentMessage"] == target
    return {
        "message": "Let's practise together.", "reaction": "encouraging",
        "responseQuality": "UNCLEAR" if unknown else "ADEQUATE" if observed else "PARTIAL",
        "followUpQuestion": "Try again?", "correction": {"needed": False},
        "memoryUpdates": [], "recommendedAction": "GIVE_HINT",
        "teachingAction": "GIVE_HINT", "modelSentence": None,
        "activityComplete": False, "shouldRetry": False if unknown else not observed,
        "hintLevel": 0, "detectedSkills": [], "remainingSkills": [],
    }


def test_local_contract_evaluation_writes_report(tmp_path):
    def urlopen_mock(request, timeout):
        body = json.loads(request.data)
        return io.BytesIO(json.dumps(fake_success(body)).encode("utf-8"))

    report = tmp_path / "baseline.json"
    with patch("training.class1_pilot.urlopen", side_effect=urlopen_mock):
        assert evaluate_live("http://127.0.0.1:8002/v1/brain/respond", report)
    result = json.loads(report.read_text(encoding="utf-8"))
    assert len(result) == 17
    assert all(item["passed"] for item in result)


def test_contract_evaluation_rejects_remote_url_and_bad_payload(tmp_path):
    with pytest.raises(ValueError, match="Only a local"):
        evaluate_live("https://example.com/collect", tmp_path / "none.json")
    with patch("training.class1_pilot.urlopen", return_value=io.BytesIO(b'{}')):
        assert not evaluate_live("http://localhost:8002/v1/brain/respond", tmp_path / "bad.json")
    assert not all(row["passed"] for row in json.loads((tmp_path / "bad.json").read_text()))
