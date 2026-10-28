"""Security and feature-boundary checks for the Node-to-Python bridge."""
import asyncio

from httpx import ASGITransport, AsyncClient

from server.main import app


PAYLOAD = {
    "grade": 1,
    "levelId": "g01-l01",
    "studentMessage": "am",
    "currentQuestion": "Say the word am.",
    "preferredExplanationLanguage": "English",
}


async def call(path="/v1/brain/respond", *, headers=None, payload=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=payload or PAYLOAD, headers=headers)


def test_local_development_keeps_existing_bridge(monkeypatch):
    monkeypatch.setenv("TALKORA_ENV", "development")
    monkeypatch.delenv("TALKORA_SERVICE_KEY", raising=False)
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    response = asyncio.run(call())
    assert response.status_code == 200, response.text
    assert response.json()["activityComplete"] is False


def test_configured_secret_requires_correct_header(monkeypatch):
    monkeypatch.setenv("TALKORA_ENV", "production")
    monkeypatch.setenv("TALKORA_SERVICE_KEY", "a" * 40)
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    assert asyncio.run(call()).status_code == 401
    assert asyncio.run(call(headers={"X-Talkora-Service-Key": "wrong"})).status_code == 401
    valid = asyncio.run(call(headers={"X-Talkora-Service-Key": "a" * 40}))
    assert valid.status_code == 200, valid.text


def test_production_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("TALKORA_ENV", "production")
    monkeypatch.delenv("TALKORA_SERVICE_KEY", raising=False)
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    assert asyncio.run(call()).status_code == 503


def test_production_short_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("TALKORA_ENV", "production")
    monkeypatch.setenv("TALKORA_SERVICE_KEY", "short")
    assert asyncio.run(call(headers={"X-Talkora-Service-Key": "short"})).status_code == 503


def test_node_environment_production_does_not_skip_auth(monkeypatch):
    monkeypatch.delenv("TALKORA_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("TALKORA_SERVICE_KEY", raising=False)
    assert asyncio.run(call()).status_code == 503


def test_production_research_chat_disabled(monkeypatch):
    monkeypatch.setenv("TALKORA_ENV", "production")
    monkeypatch.setenv("TALKORA_SERVICE_KEY", "a" * 40)
    monkeypatch.delenv("TALKORA_ENABLE_EXPERIMENTAL_CHAT", raising=False)
    response = asyncio.run(call(
        "/chat", headers={"X-Talkora-Service-Key": "a" * 40},
        payload={"level_id": "g01-l01", "message": "hello"},
    ))
    assert response.status_code == 404
