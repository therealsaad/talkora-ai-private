"""Only the optional research /chat seed is stored outside source control.

The authenticated Class 1 syllabus lives in canonical source and does not
require the untracked experimental dataset to exist in CI.
"""
import json
from pathlib import Path
import pytest

def test_optional_experimental_chat_seed():
    root = Path(__file__).resolve().parents[1]
    path = root / 'datasets/curriculum/seed.json'
    if not path.is_file():
        pytest.skip('Optional experimental chat seed is not versioned in GitHub; authenticated bridge still tested')
    data = json.loads(path.read_text(encoding='utf-8'))
    assert len(data) == 3
    assert len({item['level_id'] for item in data}) == len(data)
    assert all(item['objective'] and item['target_phrases'] for item in data)
