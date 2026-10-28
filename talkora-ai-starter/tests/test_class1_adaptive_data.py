"""V2 synthetic data: all approved targets across splits, no repeated prompts."""
import json

from training.class1_adaptive_data import build_examples, prepare
from training.class1_pilot import load_rows
from server.class1_adaptive import APPROVED_WORDS


def test_generated_examples_are_syllabus_grounded_and_held_out(tmp_path):
    dataset = build_examples()
    assert {key: len(value) for key, value in dataset.items()} == {
        "train": 192, "validation": 24, "test": 24,
    }
    # V2 evaluates in-syllabus teaching across all ten approved words. The
    # *prompts*, not the target vocabulary, must be distinct across splits.
    assert all({row["metadata"]["target"] for row in split} == APPROVED_WORDS
               for split in dataset.values())
    seen_prompts = set()
    for rows in dataset.values():
        for row in rows:
            signature = (row["messages"][0]["content"], row["messages"][1]["content"])
            assert signature not in seen_prompts
            seen_prompts.add(signature)
            assert row["metadata"]["level_id"] == "g01-l01"
            assert row["metadata"]["reviewed"] is False
            assert row["metadata"]["synthetic"] is True
            assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]
            assert set(json.loads(row["messages"][2]["content"])) == {"hint"}
            prompt = json.loads(row["messages"][1]["content"])
            assert "My First Day" in prompt["lesson_unit"]
            assert prompt["scaffold_mode"] in {"MODEL", "GUIDE", "PRACTISE", "EXTEND"}
    assert len(seen_prompts) == 240
    folder = tmp_path / "out"
    assert prepare(folder) == {"train": 192, "validation": 24, "test": 24}
    assert len(load_rows(folder / "train.jsonl")) == 192
