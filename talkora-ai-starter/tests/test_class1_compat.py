"""Offline tests; mock Qwen so no Ollama model download or AWS credentials needed."""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
import server.class1 as class1

@pytest.fixture(autouse=True)
def pilot(monkeypatch):
    monkeypatch.setenv('TALKORA_CLASS1_QWEN_PILOT','true')
    async def hint(*args, **kwargs): return 'Let us blend the letters together.'
    monkeypatch.setattr(class1,'query_qwen',hint)


def request(**updates):
    body={'grade':1,'levelId':'g01-l01','studentMessage':'at',
          'currentQuestion':'Say the word at.', 'preferredExplanationLanguage':'English'}
    body.update(updates)
    async def send():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            return await client.post('/v1/brain/respond', json=body)
    return asyncio.run(send())


def test_correct_word_is_not_a_pronunciation_certificate():
    r=request(); assert r.status_code==200, r.text
    data=r.json()
    assert data['responseQuality']=='ADEQUATE'
    assert data['detectedSkills']==[]
    assert data['activityComplete'] is False and data['memoryUpdates']==[]
    assert 'perfect' not in data['message'].lower()


def test_wrong_word_is_guided_not_punished():
    data=request(studentMessage='in').json()
    assert data['responseQuality']=='PARTIAL'
    assert data['shouldRetry'] is True
    assert data['modelSentence']=='Look at me.'


def test_unresolved_teacher_target_is_not_assumed():
    data=request(currentQuestion='What did you hear?', activityTitle='Listening').json()
    assert data['responseQuality']=='UNCLEAR'
    assert data['activityComplete'] is False


def test_refuses_other_lessons():
    assert request(levelId='g01-l02').status_code==422
    assert request(grade=4).status_code==422


def test_disabled_pilot(monkeypatch):
    monkeypatch.setenv('TALKORA_CLASS1_QWEN_PILOT','false')
    assert request().status_code==403


def test_existing_kg_route_still_present():
    r=request(grade=0,levelId='g00-l02',studentMessage='apple')
    assert r.status_code==422


def test_phrase_detection():
    assert class1.active_target('Look __ me. Choose the missing word.')=='at'
    assert class1.active_target('Build a sentence.', 'Put these words in order: I / am / Sam.')=='i am sam'
    assert class1.active_target('Listen carefully. Which word is in?')=='in'


def test_hint_filters_unsafe_claims():
    assert class1.safe_line('Your pronunciation is perfect!')==''
    assert class1.safe_line('Look at the picture!')==''
