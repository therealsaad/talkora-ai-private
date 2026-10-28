"""Full FastAPI route smoke tests without TestClient's threaded portal."""
import asyncio

from httpx import ASGITransport, AsyncClient
from server.main import app
import server.class1 as class1


async def call(body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/brain/respond", json=body)


def payload(**changes):
    body = {
        "grade": 1, "levelId": "g01-l01", "studentMessage": "up",
        "currentQuestion": "Find on.", "activityTitle": "Word practice",
        "preferredExplanationLanguage": "English",
    }
    body.update(changes)
    return body


def test_new_model_hint_gate_off_by_default(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    monkeypatch.delenv("TALKORA_CLASS1_HINTS_APPROVED", raising=False)

    async def must_not_call(*args, **kwargs):
        raise AssertionError("Qwen must not run without model-hint approval")

    monkeypatch.setattr(class1.httpx, "AsyncClient", must_not_call)
    result = asyncio.run(call(payload()))
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["responseQuality"] == "PARTIAL"
    assert data["activityComplete"] is False
    assert data["memoryUpdates"] == []


def test_repeat_micro_activity_keeps_existing_response_guard(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    monkeypatch.setenv("TALKORA_CLASS1_HINTS_APPROVED", "true")
    result = asyncio.run(call(payload(
        studentMessage="am", currentQuestion="Say the word am.",
        activityTitle="Listen and repeat")))
    assert result.status_code == 200, result.text
    data = result.json()
    assert "say it together" in data["message"].lower()
    assert data["followUpQuestion"] == "Can you say 'am' once more?"
    assert data["activityComplete"] is False


def test_wrong_grade_and_level_fail_closed(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    assert asyncio.run(call(payload(levelId="g01-l02"))).status_code == 422
    assert asyncio.run(call(payload(grade=4))).status_code == 422
    assert asyncio.run(call(payload(grade=0, levelId="g00-l02"))).status_code == 422


def test_pilot_route_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "false")
    assert asyncio.run(call(payload())).status_code == 403


def test_current_lesson_requires_teacher_review():
    # This is why a successful route smoke test is not production approval.
    assert class1.LESSON["teacher_review_required"] is True
    assert class1.LESSON["alignment_status"] == "FOUNDATIONS_DRAFT_NOT_BALBHARATI_CHAPTER_VERIFIED"
