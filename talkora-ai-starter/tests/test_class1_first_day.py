from server.class1_first_day import SCENES, first_day_voice_reply

def test_all_ten_school_scenes_have_models():
    assert len(SCENES) == 10
    for title, (_, model) in SCENES.items():
        result = first_day_voice_reply('en', title, '', "I don't know", 0)
        assert result is not None
        assert model in result['follow']
        assert result['retry'] is True

def test_school_questions_get_home_language_help():
    hindi = first_day_voice_reply('hi', 'Ding dong! The school bell', '', 'घंटी का मतलब क्या है?', 0)
    marathi = first_day_voice_reply('mr', 'Skip like a bunny', '', 'मला समजत नाही', 0)
    assert 'घंटी' in hindi['message']
    assert 'शाळ' not in hindi['message']
    assert 'उड्या' in marathi['message']
    assert 'I can skip.' in marathi['follow']

def test_transcript_word_is_not_a_pronunciation_score():
    result = first_day_voice_reply('en', 'Run in the playground', '', 'run', 0)
    assert result['quality'] == 'ADEQUATE'
    assert result['action'] == 'ASK_FOLLOW_UP'
    assert 'I can run.' in result['follow']

def test_unrelated_activity_is_not_hijacked():
    assert first_day_voice_reply('en', 'Listen am', '', 'am', 0) is None


def test_v3_first_day_uses_contextual_qwen_for_every_reply(monkeypatch):
    import asyncio
    import server.class1 as class1
    from server.compat import BrainRequest
    calls = []
    async def fake_model(language, title, question, transcript, hint_level, decision):
        calls.append((title, transcript, decision['retry']))
        return f'I heard {transcript}. Let us learn skip with your hopping fingers!'
    monkeypatch.setattr(class1, 'first_day_qwen_coach', fake_model)
    request = BrainRequest(grade=1, levelId='g01-l01', activityTitle='Skip like a bunny',
                           currentQuestion='Say I can skip.', studentMessage='jump',
                           preferredExplanationLanguage='English')
    answer = asyncio.run(class1.respond_class1(request))
    assert answer['message'].startswith('I heard jump.')
    assert calls == [('Skip like a bunny', 'jump', True)]
    assert answer['modelSentence'] == 'I can skip.'
    assert answer['shouldRetry'] is True
    assert answer['activityComplete'] is False


def test_v3_missing_local_qwen_is_not_silently_replaced_by_script(monkeypatch):
    import asyncio
    import server.class1 as class1
    from fastapi import HTTPException
    from server.compat import BrainRequest
    async def failed_model(*args, **kwargs):
        raise HTTPException(503, 'CLASS1_LOCAL_QWEN_UNAVAILABLE')
    monkeypatch.setattr(class1, 'first_day_qwen_coach', failed_model)
    request = BrainRequest(grade=1, levelId='g01-l01', activityTitle='Skip like a bunny',
                           currentQuestion='Say I can skip.', studentMessage='skip')
    import pytest
    with pytest.raises(HTTPException) as caught:
        asyncio.run(class1.respond_class1(request))
    assert caught.value.status_code == 503


def test_local_qwen_turn_reads_actual_child_answer_and_rejects_fake_mastery(monkeypatch):
    import asyncio
    import json
    import pytest
    from fastapi import HTTPException
    import server.class1_first_day as teacher

    class Reply:
        def __init__(self, message):
            self.message = message
        def raise_for_status(self):
            return None
        def json(self):
            return {'message': {'content': json.dumps({'message': self.message})}}

    class LocalQwen:
        def __init__(self, message):
            self.message = message
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, url, json):
            assert url == 'http://127.0.0.1:11434/api/chat'
            assert json['model'] == 'qwen3:4b-instruct'
            assert 'jump' in json['messages'][1]['content']
            assert 'I can skip.' in json['messages'][1]['content']
            return Reply(self.message)

    decision = teacher.first_day_voice_reply('en', 'Skip like a bunny',
                                             'I can skip', 'jump', 0)
    monkeypatch.setattr(teacher.httpx, 'AsyncClient', lambda **kw:
                        LocalQwen('I heard jump! Our word is skip. Try a little bunny hop.'))
    good = asyncio.run(teacher.first_day_qwen_coach('en', 'Skip like a bunny',
                                                       'I can skip', 'jump', 0, decision))
    assert 'I heard jump' in good
    monkeypatch.setattr(teacher.httpx, 'AsyncClient', lambda **kw:
                        LocalQwen('Perfect! Your answer is exactly right!'))
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(teacher.first_day_qwen_coach('en', 'Skip like a bunny',
                                                 'I can skip', 'jump', 0, decision))
    assert blocked.value.status_code == 502
