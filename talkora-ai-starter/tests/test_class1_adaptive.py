"""Offline adaptive Class 1 tests; never download models or send student data."""
import asyncio
from types import SimpleNamespace

import httpx

from server.class1_adaptive import (APPROVED_WORDS, CURRICULUM, curriculum_context,
                                    has_supported_school_sentence,
                                    is_simple_repeat, select_teaching_plan)
from server.compat import BrainRequest, brain_respond
import server.class1 as class1


def req(**updates):
    values = {
        "currentQuestion": "Say the word at.", "activityTitle": "Listen and repeat",
        "studentMessage": "at", "hintLevel": 0,
        "waitingForRetry": False, "recentMistakes": [],
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_scaffolds_use_existing_fields_not_iq():
    assert select_teaching_plan(req(), True, "at").mode == "PRACTISE"
    assert select_teaching_plan(req(studentMessage="in"), False, "at").mode == "MODEL"
    assert select_teaching_plan(req(hintLevel=2), True, "at").mode == "MODEL"
    assert select_teaching_plan(req(waitingForRetry=True), True, "at").mode == "MODEL"
    assert select_teaching_plan(req(recentMistakes=["at"]), True, "at").mode == "GUIDE"
    assert select_teaching_plan(req(recentMistakes=["at", "in"]), True, "at").mode == "MODEL"
    assert select_teaching_plan(req(studentMessage="Look at me."), True, "at").mode == "EXTEND"
    assert select_teaching_plan(req(studentMessage="I can say on."), True, "on").mode == "EXTEND"
    assert select_teaching_plan(req(studentMessage="hello"), None, None).mode == "GUIDE"
    assert select_teaching_plan(req(currentQuestion="My first day at school",
                                    studentMessage="I am at school."), None, None).mode == "EXTEND"


def test_syllabus_alignment_is_only_the_approved_lesson():
    assert CURRICULUM["levelId"] == "g01-l01"
    assert "1.1 My First Day" in CURRICULUM["syllabus"]["unit"]
    assert APPROVED_WORDS == set("am an at in is it on up school walk".split())
    assert "school" not in curriculum_context("Say the word at", "Listening")["approved_vocabulary"]
    assert "school" in curriculum_context("Tell me about school", "First Day")["approved_vocabulary"]
    assert has_supported_school_sentence("Tell me about school", "School talk", "I am at school.")
    assert not has_supported_school_sentence("Say the word at", "Listening", "I am at school.")
    assert is_simple_repeat("Say the word at", "Listen and repeat", "at")
    assert not is_simple_repeat("Tell me about school", "School talk", None)


def test_explicit_school_walk_words_are_understood_without_expanding_other_levels():
    assert class1.active_target("Say the word walk.") == "walk"
    assert class1.active_target("Find school.") == "school"
    assert class1.active_target("Tell me about school") is None
    assert class1.observed_target("I walk to school.", "walk") is True
    assert class1.safe_line("This response is much too long for a child to listen to while learning new little words.") == ""


def test_simple_repeat_does_not_call_ollama(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")

    async def must_not_call(*args, **kwargs):
        raise AssertionError("Fixed repeat feedback should not call Ollama")

    monkeypatch.setattr(class1, "query_qwen", must_not_call)
    data = asyncio.run(brain_respond(BrainRequest(**{
        "grade": 1, "levelId": "g01-l01", "studentMessage": "at",
        "currentQuestion": "Say the word at.",
        "activityTitle": "Listen and repeat", "preferredExplanationLanguage": "English",
    })))
    assert data["responseQuality"] == "ADEQUATE"
    assert data["activityComplete"] is False
    assert data["memoryUpdates"] == []
    assert data["followUpQuestion"] == "Can you say 'at' once more?"


def test_guided_school_chat_receives_scaffold_and_preserves_schema(monkeypatch):
    monkeypatch.setenv("TALKORA_CLASS1_QWEN_PILOT", "true")
    plans = []

    async def fake_model(*args, **kwargs):
        plans.append(kwargs["plan"].mode)
        return "Let's practise a little school sentence together."

    monkeypatch.setattr(class1, "query_qwen", fake_model)
    data = asyncio.run(brain_respond(BrainRequest(**{
        "grade": 1, "levelId": "g01-l01", "studentMessage": "I am at school.",
        "currentQuestion": "Tell me about your first day at school.",
        "activityTitle": "School talk", "preferredExplanationLanguage": "Hindi",
        "recentMistakes": ["at"], "hintLevel": 1,
    })))
    assert plans == ["GUIDE"]
    assert data["responseQuality"] == "ADEQUATE"  # Only pre-approved sentence evidence.
    assert "school" in data["followUpQuestion"]
    assert data["activityComplete"] is False
    assert data["memoryUpdates"] == []
    assert data["detectedSkills"] == []


def test_qwen_unavailable_uses_safe_deterministic_baseline(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    hint = asyncio.run(class1.query_qwen("school", "school", True, "en", "Say school"))
    assert hint == ""
