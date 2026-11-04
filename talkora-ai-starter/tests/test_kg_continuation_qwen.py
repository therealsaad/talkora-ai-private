"""KG2–5 opt-in Qwen context tests: no Ollama/network, no publishing."""
import json

from fastapi.testclient import TestClient
from server.main import app
import server.compat as compat

client = TestClient(app)

class _OllamaReply:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": json.dumps({
            "message": "A lion is a big cat. Now say the letter L.",
            "reaction": "encouraging",
            "followUpQuestion": None,
            "activityComplete": True,  # malicious model cannot set this
            "memoryUpdates": [{"key": "private", "value": "unsafe"}],
        })}}

class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.calls.append(json)
        _FakeClient.last_request = json
        return _OllamaReply()

def payload(level="g00-l03", letter="L", word="lion", **updates):
    obj = {
        "grade": 0, "levelId": level, "studentName": "Learner",
        "studentMessage": "Why is a lion called sher?",
        "currentQuestion": "Say the letter " + letter,
        "activityTitle": "Letter " + letter,
        "allowedVocabulary": [letter] + ([word] if word else []),
        "preferredExplanationLanguage": "Hindi",
    }
    obj.update(updates)
    return obj

def test_continuation_gate_off_by_default(monkeypatch):
    monkeypatch.delenv("TALKORA_KG2_5_QWEN_PILOT", raising=False)
    assert client.post("/v1/brain/respond", json=payload()).status_code == 403

def test_all_authorized_current_levels_route_but_never_finish_or_store_history(monkeypatch):
    monkeypatch.setenv("TALKORA_KG2_5_QWEN_PILOT", "true")
    monkeypatch.setattr(compat.httpx, "AsyncClient", _FakeClient)
    cases = [
        ("g00-l02", "E", ""), ("g00-l03", "L", "lion"),
        ("g00-l04", "R", "rabbit"), ("g00-l05", "W", "wolf"),
        ("g00-l05", "Y", "yak"),
    ]
    for level, letter, word in cases:
        res = client.post("/v1/brain/respond", json=payload(level, letter, word))
        assert res.status_code == 200, res.text
        assert res.json()["activityComplete"] is False
        assert res.json()["memoryUpdates"] == []
        context = _FakeClient.last_request["messages"][0]["content"]
        assert level in context
        assert '"currentLetter": "' + letter + '"' in context
        assert '"currentQuestion": "Say the letter ' + letter + '"' in context
        if level == "g00-l02":
            assert '"pictureWord": ""' in context

def test_rejects_unsafe_context_and_unpublished_levels_before_ollama(monkeypatch):
    monkeypatch.setenv("TALKORA_KG2_5_QWEN_PILOT", "true")
    monkeypatch.setattr(compat.httpx, "AsyncClient", _FakeClient)
    cases = [
        payload(level="g00-l06"), payload(level="g00-l10"),
        payload(grade=4), payload(currentQuestion="Say the letter Z"),
        payload(allowedVocabulary=["L", "elephant"]),
        payload(allowedVocabulary=["L", "lion", "phone"]),
        payload(studentName="Real child"),
        payload(conversationHistory=["personal details"]),
        payload(recentMistakes=["contains student history"]),
    ]
    for data in cases:
        res = client.post("/v1/brain/respond", json=data)
        assert res.status_code == 422, (data, res.status_code, res.text)

def test_class1_and_kg1_gates_remain_separate(monkeypatch):
    monkeypatch.setenv("TALKORA_KG2_5_QWEN_PILOT", "true")
    monkeypatch.delenv("TALKORA_CLASS1_QWEN_PILOT", raising=False)
    assert client.post("/v1/brain/respond", json=payload(grade=1, levelId="g01-l01")).status_code == 403
    assert client.post("/v1/brain/respond", json=payload(level="g00-l06")).status_code == 422
