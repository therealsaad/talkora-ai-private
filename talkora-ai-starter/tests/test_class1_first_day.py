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
    async def fake_model(language, title, question, transcript, hint_level, decision, history=None):
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

def test_v3_brain_endpoint_reaches_adaptive_coach_without_touching_legacy(monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import app
    import server.class1 as class1

    calls = []
    async def fake_coach(language, title, question, transcript, hint_level, decision, history=None):
        calls.append((language, title, transcript, decision['retry']))
        return 'You told me jump! Our school action word is skip. Let us try skip.'

    monkeypatch.setenv('TALKORA_CLASS1_QWEN_PILOT', 'true')
    monkeypatch.setattr(class1, 'first_day_qwen_coach', fake_coach)
    client = TestClient(app)
    answer = client.post('/v1/brain/respond', json={
        'grade': 1, 'levelId': 'g01-l01',
        'activityTitle': 'Skip like a bunny',
        'digitalType': 'FIRST_DAY_VOICE_SCENE',
        'currentQuestion': 'Say in English what you can do. I can skip.',
        'studentMessage': 'jump',
        'preferredExplanationLanguage': 'English',
    })
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result['message'].startswith('You told me jump!')
    assert result['modelSentence'] == 'I can skip.'
    assert result['shouldRetry'] is True
    assert result['activityComplete'] is False
    assert calls == [('en', 'Skip like a bunny', 'jump', True)]

def test_first_day_variations_match_node_evidence_without_false_praise():
    from server.class1_first_day import first_day_voice_reply
    for scene, speech in [
        ('Skip like a bunny', 'skipping'), ('Run in the playground', 'running'),
        ('Give Miss Julie a grin', 'grin'), ('Ding dong!', 'ringing'),
        ('Jump like a frog', 'jumping'), ('Time to go into class', 'classroom'),
    ]:
        decision = first_day_voice_reply('en', scene, 'Say it.', speech, 0)
        assert decision is not None
        assert decision['retry'] is False, (scene, speech)
    for speech in ('billi', 'cat', 'skip?', 'what does skip mean?', 'मदद skip'):
        decision = first_day_voice_reply('en', 'Skip like a bunny', 'Say skip.', speech, 0)
        assert decision['retry'] is True, speech


def test_first_day_kid_uses_hindi_example_but_stays_on_approved_english_target():
    from server.class1_first_day import first_day_voice_reply
    decision = first_day_voice_reply('hi', 'Skip like a bunny',
                                     'Tell me in English.', 'billi', 1)
    assert decision['model'] == 'I can skip.'
    assert decision['retry'] is True
    assert decision['quality'] == 'PARTIAL'


def test_first_day_live_qwen_uses_bounded_conversation_history(monkeypatch):
    import asyncio
    import json
    import server.class1_first_day as teacher
    captured = {}

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {'message': {'content': json.dumps({
                'message': 'I heard you! Our current English action word is skip. Try again.'
            })}}
    class MockOllama:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, url, json):
            captured.update(json)
            return Response()

    monkeypatch.setattr(teacher.httpx, 'AsyncClient', lambda **kw: MockOllama())
    decision = teacher.first_day_voice_reply('en', 'Skip like a bunny',
                                              'I can skip.', 'jump', 1)
    history = ['student: I said jump.', 'missJulie: Try saying skip.',
               'student: jump again.', 'missJulie: Let us learn together.',
               'student: still not sure.', 'missJulie: One little step.',
               'student: last try was jump.']
    result = asyncio.run(teacher.first_day_qwen_coach(
        'en', 'Skip like a bunny', 'I can skip.', 'jump', 1, decision,
        history=history,
    ))
    context = json.loads(captured['messages'][1]['content'])
    assert len(context['recent_dialogue']) == 6
    assert context['recent_dialogue'][0].startswith('missJulie: Try')
    assert context['recent_dialogue'][-1] == 'student: last try was jump.'
    assert 'skip' in result
    assert context['target'] == 'skip'


def test_poem_pair_requires_both_taught_lines_not_just_skip():
    from server.class1_first_day import first_day_voice_reply, poem_attempt_is_complete
    title = 'Poem lines 1–2: skip and run'
    assert not poem_attempt_is_complete(title, 'skip')
    assert not poem_attempt_is_complete(title, 'What does skip mean?')
    assert poem_attempt_is_complete(title, 'See me skip. See me run.')
    one = first_day_voice_reply('en', title, '', 'skip', 0)
    assert one['retry'] is True
    two = first_day_voice_reply('en', title, '', 'See me skip. See me run.', 0)
    assert two['retry'] is False

def test_poem_full_recital_needs_multiple_stanzas():
    from server.class1_first_day import poem_attempt_is_complete, first_day_voice_reply
    title='Poem finale: recite My First Day'
    assert not poem_attempt_is_complete(title, 'skip run walk grin')
    assert poem_attempt_is_complete(title, (
        'See me skip. See me run. I am going to school like everyone. '
        'See me walk. See me grin. When the bell rings I go in. '
        'See me jump. See me play. I am in Grade One! Hip hip hurray!'
    ))
    hint = first_day_voice_reply('hi', title, '', 'I can skip', 2)
    assert hint['retry'] is True


def test_poem_retry_repeats_same_two_lines_when_child_needs_help():
    from server.class1_first_day import first_day_voice_reply
    decision = first_day_voice_reply('hi', 'Poem lines 1–2: skip and run',
                                     'Say both lines', 'बिल्ली', 2)
    assert decision['retry'] is True
    assert decision['follow'].count('See me skip') == 2
    assert decision['follow'].count('See me run') == 2
    assert 'skip' in decision['model']
