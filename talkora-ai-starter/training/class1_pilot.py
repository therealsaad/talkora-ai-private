"""Offline Class 1 Qwen pilot: prepare, evaluate, and optionally fine-tune.

This never edits the running Ollama model, FastAPI routes, or student records.
Training examples are synthetic and must be reviewed before production use.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LESSON_FILE = ROOT / "phase3" / "class1.json"
DATA_DIR = ROOT / "datasets" / "training" / "class1-pilot"
MODEL_ID = "Qwen/Qwen3-1.7B"
LEVEL_ID = "g01-l01"
FOUNDATION_WORDS = ("am", "an", "at", "in", "is", "it", "on", "up")

# Keep the response contract identical to server.class1.query_qwen: a JSON hint,
# not a grade, completion decision, pronunciation certificate, or new question.
SYSTEM_PROMPT = (
    "You are Miss Julie, a supportive English tutor for Class 1 beginners. "
    "The text is a speech transcript, NOT proof of pronunciation. "
    "Never grade, declare correct or incorrect, certify pronunciation, "
    "claim to see images, or ask for personal information. "
    "Stay within the eight approved two-letter words and the supplied teacher question. "
    "Write one tiny beginner-friendly teaching hint, maximum 12 words. "
    "Use a brief Hindi or Marathi hint only when requested. "
    'Return only a JSON object with one string field: {"hint":"..."}.'
)

HINTS = {
    "en": {
        "heard": ("Let's blend the two sounds slowly together.", "Try saying each sound clearly and gently."),
        "different": ("Listen to both sounds, then try the little word.", "Let's practise the two sounds together once more."),
        "unsure": ("Take your time; listen once, then try with me.", "Let's listen carefully and try the word together."),
    },
    "hi": {
        "heard": ("बहुत अच्छा प्रयास, अब धीरे से दोहराओ।", "दोनों अक्षरों की आवाज़ मिलाकर बोलो।"),
        "different": ("ध्यान से सुनो, फिर शब्द बोलने की कोशिश करो।", "चलो दोनों आवाज़ें मिलाकर फिर बोलें।"),
        "unsure": ("कोई जल्दी नहीं, मेरे साथ धीरे-धीरे बोलो।", "पहले सुनो, फिर आराम से बोलने की कोशिश करो।"),
    },
    "mr": {
        "heard": ("छान प्रयत्न, आता हळूच पुन्हा म्हण।", "दोन्ही आवाज एकत्र करून शब्द म्हण।"),
        "different": ("नीट ऐक आणि मग शब्द पुन्हा म्हण।", "चला, दोन्ही आवाज हळूहळू जोडूया।"),
        "unsure": ("घाई नको, माझ्यासोबत हळू बोल।", "आधी ऐक, मग पुन्हा प्रयत्न कर।"),
    },
}


def load_lesson(path: Path = LESSON_FILE) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Missing local Class 1 lesson: {path}. Do not invent textbook content.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Class 1 lesson must be a JSON object")
    raw = data.get("approved_foundation_words")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Class 1 lesson has no approved_foundation_words")
    words = {str(item).strip().lower() for item in raw}
    if words != set(FOUNDATION_WORDS):
        raise ValueError(f"Unexpected approved word list: {sorted(words)}; review before training")
    if not isinstance(data.get("model_sentences"), dict):
        raise ValueError("Class 1 lesson has no model_sentences mapping")
    return data


def build_examples(lesson: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Hold out entire words to avoid near-identical train/test leakage."""
    approved = sorted({str(x).lower() for x in lesson["approved_foundation_words"]})
    if len(approved) < 4:
        raise ValueError("Need at least four approved words for word-held-out evaluation")
    split_by_word = {word: ("train" if i < len(approved) - 2 else
                            "validation" if i == len(approved) - 2 else "test")
                     for i, word in enumerate(approved)}
    output: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for index, word in enumerate(approved):
        different = approved[(index + 1) % len(approved)]
        for lang in ("en", "hi", "mr"):
            for scenario in ("heard", "different", "unsure"):
                for variant, hint in enumerate(HINTS[lang][scenario]):
                    transcript = (
                        word if scenario == "heard" else
                        different if scenario == "different" else
                        "I don't know"
                    )
                    question = (f"Say the word {word}." if variant == 0 else
                                f"Repeat the word {word}.")
                    context = {
                        "target": word,
                        "transcript": transcript,
                        "word_visible_in_transcript": scenario == "heard",
                        "support_language": lang,
                        "teacher_question": question,
                        "approved_vocabulary": approved,
                    }
                    output[split_by_word[word]].append({
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                            {"role": "assistant", "content": json.dumps({"hint": hint}, ensure_ascii=False)},
                        ],
                        "metadata": {"level_id": LEVEL_ID, "target": word,
                                     "scenario": scenario, "language": lang},
                    })
    return output


def prepare(lesson_file: Path = LESSON_FILE, output_dir: Path = DATA_DIR) -> dict[str, int]:
    lesson = load_lesson(lesson_file)
    examples = build_examples(lesson)
    output_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in examples.items():
        with (output_dir / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = {split: len(rows) for split, rows in examples.items()}
    print("Prepared synthetic Class 1 pilot:", counts)
    print("Review every example before training. No private student speech is included.")
    return counts


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Missing {path}. Run 'prepare' first.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"Empty training split: {path}")
    for row in rows:
        roles = [message.get("role") for message in row.get("messages", [])]
        if roles != ["system", "user", "assistant"]:
            raise ValueError(f"Unexpected message contract in {path}")
        answer = json.loads(row["messages"][2]["content"])
        if set(answer) != {"hint"} or not isinstance(answer["hint"], str):
            raise ValueError(f"Training target must be a single JSON hint in {path}")
    return rows


def encode_example(tokenizer: Any, row: dict[str, Any], max_length: int) -> dict[str, list[int]]:
    """Train only assistant answer tokens, not system text or student transcript."""
    messages = row["messages"]
    prefix = tokenizer.apply_chat_template(
        messages[:2], tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    full = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False, enable_thinking=False
    )
    prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]
    if full_ids[:len(prefix_ids)] != prefix_ids:
        raise ValueError("Chat-template prefix mismatch; refusing to train on user/system tokens")
    if len(full_ids) > max_length:
        raise ValueError("Training sample exceeds max_length; raise it or shorten the approved prompt")
    if len(full_ids) <= len(prefix_ids):
        raise ValueError("No assistant tokens to supervise")
    return {"input_ids": full_ids, "attention_mask": [1] * len(full_ids),
            "labels": [-100] * len(prefix_ids) + full_ids[len(prefix_ids):]}


def evaluate_live(url: str, output_path: Path) -> bool:
    """Contract baseline against local port 8002; never send real student data."""
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("Only a local, HTTP Qwen pilot endpoint is allowed")
    cases = []
    for index, word in enumerate(FOUNDATION_WORDS):
        cases.append((word, word, "ADEQUATE", False))
        cases.append((word, FOUNDATION_WORDS[(index + 1) % len(FOUNDATION_WORDS)], "PARTIAL", True))
    cases.append((None, "hello", "UNCLEAR", False))
    results: list[dict[str, Any]] = []
    for target, transcript, quality, retry in cases:
        body = {
            "grade": 1, "levelId": LEVEL_ID, "studentMessage": transcript,
            "currentQuestion": f"Say the word {target}." if target else "What did you hear?",
            "activityTitle": f"Listen and repeat {target}" if target else "Listening",
            "preferredExplanationLanguage": "English",
        }
        failure = None
        data: dict[str, Any] = {}
        try:
            request = Request(url, json.dumps(body).encode("utf-8"),
                              {"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=90) as response:
                data = json.load(response)
            expected_keys = {"message", "reaction", "responseQuality", "followUpQuestion",
                             "correction", "memoryUpdates", "recommendedAction", "teachingAction",
                             "modelSentence", "activityComplete", "shouldRetry", "hintLevel",
                             "detectedSkills", "remainingSkills"}
            if not expected_keys.issubset(data):
                failure = f"Missing keys: {sorted(expected_keys - set(data))}"
            elif data["responseQuality"] != quality or data["shouldRetry"] is not retry:
                failure = "Unexpected quality/retry"
            elif data["activityComplete"] is not False or data["memoryUpdates"] != []:
                failure = "Brain must not own progress or memory"
            elif not isinstance(data["message"], str) or not data["message"].strip():
                failure = "Missing teacher response"
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        results.append({"target": target, "transcript": transcript,
                        "expectedQuality": quality, "observedQuality": data.get("responseQuality"),
                        "passed": failure is None, "error": failure})
        print(f"{'PASS' if failure is None else 'FAIL'}: target={target}, spoken={transcript}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = sum(item["passed"] for item in results)
    print(f"Local contract baseline: {passed}/{len(results)} passed. Report: {output_path}")
    print("Transcript matching is NOT an acoustic pronunciation score or proof of LLM quality.")
    return passed == len(results)


def train(data_dir: Path, output_dir: Path, model_id: str, max_length: int,
          epochs: float, learning_rate: float) -> None:
    """GPU-only, low-VRAM QLoRA experiment; does not replace the Ollama model."""
    try:
        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from torch.utils.data import Dataset
        from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                  BitsAndBytesConfig, Trainer, TrainingArguments)
    except ImportError as exc:
        raise RuntimeError("Training dependencies missing. Use a separate QLoRA virtual environment.") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA PyTorch required. Do not train in the running voice-service environment.")
    if max_length < 128 or max_length > 512:
        raise ValueError("For the 6 GB pilot, max_length must be between 128 and 512")
    rows_train = load_rows(data_dir / "train.jsonl")
    rows_val = load_rows(data_dir / "validation.jsonl")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_tokens = [encode_example(tokenizer, row, max_length) for row in rows_train]
    val_tokens = [encode_example(tokenizer, row, max_length) for row in rows_val]

    class Samples(Dataset):
        def __init__(self, examples: list[dict[str, list[int]]]):
            self.examples = examples

        def __len__(self) -> int:
            return len(self.examples)

        def __getitem__(self, index: int) -> dict[str, list[int]]:
            return self.examples[index]

    def collate(batch: list[dict[str, list[int]]]) -> dict[str, Any]:
        longest = max(len(row["input_ids"]) for row in batch)
        padded = {key: [] for key in ("input_ids", "attention_mask", "labels")}
        for row in batch:
            n = longest - len(row["input_ids"])
            padded["input_ids"].append(row["input_ids"] + [tokenizer.pad_token_id] * n)
            padded["attention_mask"].append(row["attention_mask"] + [0] * n)
            padded["labels"].append(row["labels"] + [-100] * n)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in padded.items()}

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                     bnb_4bit_compute_dtype=compute_dtype,
                                     bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, quantization_config=quantization, device_map={"": 0},
        torch_dtype=compute_dtype, trust_remote_code=False
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    ))
    args = TrainingArguments(
        output_dir=str(output_dir), per_device_train_batch_size=1,
        per_device_eval_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=epochs, learning_rate=learning_rate,
        eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
        logging_steps=5, report_to="none", optim="paged_adamw_8bit",
        fp16=compute_dtype == torch.float16, bf16=compute_dtype == torch.bfloat16,
        gradient_checkpointing=True, remove_unused_columns=False,
        dataloader_num_workers=0, seed=42
    )
    trainer = Trainer(model=model, args=args, train_dataset=Samples(train_tokens),
                      eval_dataset=Samples(val_tokens), data_collator=collate)
    trainer.train()
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"QLoRA pilot adapter saved to {output_dir}")
    print("This adapter has NOT been deployed to Ollama or approved for students.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    p_prepare = actions.add_parser("prepare", help="Build reviewable synthetic dataset")
    p_prepare.add_argument("--lesson", type=Path, default=LESSON_FILE)
    p_prepare.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p_evaluate = actions.add_parser("evaluate-live", help="Run local API contract baseline")
    p_evaluate.add_argument("--url", default="http://127.0.0.1:8002/v1/brain/respond")
    p_evaluate.add_argument("--report", type=Path,
                            default=ROOT / "outputs" / "class1-pilot-baseline.json")
    p_train = actions.add_parser("train", help="Fine-tune a separate Hugging Face adapter")
    p_train.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p_train.add_argument("--output-dir", type=Path,
                         default=ROOT / "outputs" / "class1-qwen3-1.7b-qlora")
    p_train.add_argument("--model", default=MODEL_ID)
    p_train.add_argument("--max-length", type=int, default=384)
    p_train.add_argument("--epochs", type=float, default=1.0)
    p_train.add_argument("--learning-rate", type=float, default=0.0001)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.lesson, args.data_dir)
        elif args.action == "evaluate-live":
            return 0 if evaluate_live(args.url, args.report) else 1
        elif args.action == "train":
            train(args.data_dir, args.output_dir, args.model, args.max_length,
                  args.epochs, args.learning_rate)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
