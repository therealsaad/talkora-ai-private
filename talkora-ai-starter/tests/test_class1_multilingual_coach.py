"""Offline Marathi/Hindi Class 1 teaching behavior; no paid speech or LLM calls."""
import asyncio

from server.class1 import respond_class1
from server.class1_language import resolve_support_language
from server.class1_response_guard import guard_class1_response
from server.compat import BrainRequest


def response(transcript, preference='English', question='Say the word at.', **kwargs):
    req = BrainRequest(
        grade=1, levelId='g01-l01', studentMessage=transcript,
        currentQuestion=question, activityTitle='Listen and repeat',
        preferredExplanationLanguage=preference, **kwargs,
    )
    return guard_class1_response(asyncio.run(respond_class1(req)), req)


def test_explicit_marathi_overrides_english_and_teaches_english_word():
    answer = response('मला समजत नाही')
    assert answer['responseQuality'] == 'UNCLEAR'
    assert 'at' in answer['message']
    assert 'ऐक' in answer['message']
    assert answer['activityComplete'] is False


def test_hindi_request_produces_hindi_support_on_wrong_word():
    answer = response('हिंदी में समझाओ', preference='Marathi')
    assert answer['responseQuality'] == 'UNCLEAR'
    assert 'सुनो' in answer['message']
    assert 'at' in answer['message']
    assert 'बोलोगे' in answer['followUpQuestion']


def test_hindi_preference_and_correct_transcript_do_not_grade_pronunciation():
    answer = response('at', preference='Hindi')
    assert 'मैंने' in answer['message']
    assert answer['responseQuality'] == 'ADEQUATE'
    assert answer['detectedSkills'] == []
    assert answer['activityComplete'] is False


def test_devanagari_alone_is_not_a_language_classifier():
    assert resolve_support_language('English', 'नमस्ते') == 'en'
    assert resolve_support_language('Marathi', 'at') == 'mr'
    assert resolve_support_language('English', 'मराठीत समजावून सांग') == 'mr'
    assert resolve_support_language('English', 'please explain in Hindi') == 'hi'
    assert resolve_support_language('Klingon', 'hindi') is None
