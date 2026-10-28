"""Class 1 real voice-turn responses: offline, no model, Azure or Sarvam calls."""
import asyncio

from server.class1 import respond_class1
from server.class1_response_guard import guard_class1_response
from server.compat import BrainRequest


def lesson_turn(message: str, **overrides):
    payload = {
        'grade': 1, 'levelId': 'g01-l01',
        'currentQuestion': 'Tell Miss Julie one little sentence about school.',
        'activityTitle': 'First day at school',
        'studentMessage': message,
        'preferredExplanationLanguage': 'English',
    }
    payload.update(overrides)
    req = BrainRequest(**payload)
    return guard_class1_response(asyncio.run(respond_class1(req)), req)


def test_school_word_gets_sentence_model_not_generic_loop(monkeypatch):
    monkeypatch.delenv('TALKORA_CLASS1_HINTS_APPROVED', raising=False)
    result = lesson_turn('school')
    assert result['responseQuality'] == 'PARTIAL'
    assert result['shouldRetry'] is True
    assert 'I am at school.' in result['message']
    assert 'I am at school.' in result['followUpQuestion']
    assert result['modelSentence'] == 'I am at school.'
    assert result['activityComplete'] is False
    assert result['detectedSkills'] == []


def test_school_sentence_is_followed_by_a_new_small_question(monkeypatch):
    monkeypatch.delenv('TALKORA_CLASS1_HINTS_APPROVED', raising=False)
    result = lesson_turn('I am at school.')
    assert result['responseQuality'] == 'ADEQUATE'
    assert result['shouldRetry'] is False
    assert 'I walk to school.' in result['followUpQuestion']
    assert result['teachingAction'] == 'ASK_FOLLOW_UP'
    assert result['activityComplete'] is False  # Node backend owns mastery.


def test_child_who_needs_help_practises_before_extending(monkeypatch):
    monkeypatch.delenv('TALKORA_CLASS1_HINTS_APPROVED', raising=False)
    result = lesson_turn('I am at school.', recentMistakes=['school', 'walk'])
    assert result['responseQuality'] == 'ADEQUATE'
    assert 'I am at school.' in result['followUpQuestion']


def test_home_language_explanation_keeps_target_sentence_english(monkeypatch):
    monkeypatch.delenv('TALKORA_CLASS1_HINTS_APPROVED', raising=False)
    result = lesson_turn('मला समजत नाही', preferredExplanationLanguage='English')
    assert result['responseQuality'] == 'UNCLEAR'
    assert 'काही हरकत नाही' in result['message']
    assert 'I am at school.' in result['message']
    assert result['shouldRetry'] is True

    result_hi = lesson_turn('स्कूल', preferredExplanationLanguage='Hindi')
    assert 'कोई बात नहीं' in result_hi['message']
    assert 'I am at school.' in result_hi['followUpQuestion']


def test_not_an_iq_or_pronunciation_assessment(monkeypatch):
    monkeypatch.delenv('TALKORA_CLASS1_HINTS_APPROVED', raising=False)
    result = lesson_turn('I do not know')
    assert result['responseQuality'] == 'UNCLEAR'
    assert result['memoryUpdates'] == []
    assert result['activityComplete'] is False
    assert not result['correction']['needed']
    assert all(word not in result['message'].lower() for word in ('iq', 'pronunciation', 'wrong', 'perfect'))
