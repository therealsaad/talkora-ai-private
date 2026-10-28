"""Tracked pilot fixtures must work on a fresh clone without generated data."""
from server.main import LESSONS, PILOT_LESSON_FILES


def test_version_controlled_pilot_curriculum_loads():
    assert all(path.exists() for path in PILOT_LESSON_FILES)
    assert set(LESSONS) == {'g00-l01', 'g01-l01'}
    assert all(item['teacher_review_required'] is True for item in LESSONS.values())
    assert all(item['title'] for item in LESSONS.values())
