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


def test_v3_first_day_uses_qwen_only_for_novel_child_questions(monkeypatch):
    import asyncio
    import server.class1 as class1
    from server.compat import BrainRequest
    calls = []

    async def fake_model(language, title, question, transcript, hint_level, decision, history=None):
        calls.append((title, transcript, decision['retry']))
        return 'Bunnies hop happily at school. Our new word is skip.'

    monkeypatch.setattr(class1, 'first_day_qwen_coach', fake_model)
    question = 'Why do bunnies skip?'
    request = BrainRequest(grade=1, levelId='g01-l01', activityTitle='Skip like a bunny',
                           currentQuestion='Say I can skip.', studentMessage=question,
                           preferredExplanationLanguage='English')
    answer = asyncio.run(class1.respond_class1(request))
    assert 'Bunnies hop happily' in answer['message']
    assert calls == [('Skip like a bunny', question, True)]
    assert answer['modelSentence'] == 'I can skip.'
    assert answer['shouldRetry'] is True
    assert answer['activityComplete'] is False


def test_v3_routine_English_Hindi_Marathi_turns_do_not_wait_for_qwen(monkeypatch):
    import asyncio
    import server.class1 as class1
    from server.compat import BrainRequest

    async def must_not_call(*args, **kwargs):
        raise AssertionError('Routine scene feedback must not contact Qwen')

    monkeypatch.setattr(class1, 'first_day_qwen_coach', must_not_call)
    for spoken, language in [('skip', 'English'), ('मला समजत नाही', 'Marathi'),
                             ('बिल्ली', 'Hindi'), ('मांजर', 'Marathi')]:
        req = BrainRequest(grade=1, levelId='g01-l01',
                           activityTitle='Skip like a bunny',
                           currentQuestion='Say I can skip.', studentMessage=spoken,
                           preferredExplanationLanguage=language)
        result = asyncio.run(class1.respond_class1(req))
        assert result['activityComplete'] is False
        assert result['memoryUpdates'] == []
        assert result['modelSentence'] == 'I can skip.'
        assert 'I can skip.' in result['followUpQuestion']


def test_v3_open_question_when_qwen_is_offline_uses_safe_reviewed_fallback(monkeypatch):
    import asyncio
    import server.class1 as class1
    from fastapi import HTTPException
    from server.compat import BrainRequest

    async def failed_model(*args, **kwargs):
        raise HTTPException(503, 'CLASS1_LOCAL_QWEN_UNAVAILABLE')

    monkeypatch.setattr(class1, 'first_day_qwen_coach', failed_model)
    req = BrainRequest(grade=1, levelId='g01-l01',
                       activityTitle='Skip like a bunny',
                       currentQuestion='Say I can skip.',
                       studentMessage='Why do bunnies skip?',
                       preferredExplanationLanguage='English')
    result = asyncio.run(class1.respond_class1(req))
    assert result['responseQuality'] == 'UNCLEAR'
    assert result['shouldRetry'] is True
    assert result['modelSentence'] == 'I can skip.'
    assert 'Skipping is' in result['message']
    assert result['activityComplete'] is False
    assert result['detectedSkills'] == []


def test_v3_open_question_with_bad_qwen_output_uses_safe_reviewed_fallback(monkeypatch):
    import asyncio
    import server.class1 as class1
    from fastapi import HTTPException
    from server.compat import BrainRequest

    async def failed_model(*args, **kwargs):
        raise HTTPException(502, 'CLASS1_QWEN_COACHING_REJECTED')

    monkeypatch.setattr(class1, 'first_day_qwen_coach', failed_model)
    req = BrainRequest(grade=1, levelId='g01-l01',
                       activityTitle='School gate: Hello, Grade One!',
                       currentQuestion='Tell me about school.',
                       studentMessage='Why do we go to school?',
                       preferredExplanationLanguage='Marathi')
    result = asyncio.run(class1.respond_class1(req))
    assert 'शाळेत आपण' in result['message']
    assert result['modelSentence'] == 'I am happy at school.'
    assert result['activityComplete'] is False


def test_volunteered_billi_or_manjar_is_translated_without_granting_English_mastery():
    from server.class1_first_day import first_day_voice_reply
    for spoken, language in [('billi', 'hi'), ('बिल्ली', 'hi'),
                             ('मांजर', 'mr'), ('manjar', 'mr')]:
        reply = first_day_voice_reply(language, 'Skip like a bunny', '', spoken, 0)
        assert 'cat' in reply['message']
        assert 'skip' in reply['follow']
        assert reply['retry'] is True
        assert reply['quality'] == 'PARTIAL'


def test_teacher_prefers_fast_policy_for_previously_explained_help_questions():
    from server.class1_first_day import should_consult_first_day_qwen
    title = 'Skip like a bunny'
    for spoken in ('skip', 'I can skip.', 'What does skip mean?',
                   'मला समजत नाही', 'help please', 'repeat again', 'बिल्ली'):
        assert should_consult_first_day_qwen(title, spoken) is False, spoken
    for spoken in ('Why do bunnies skip?', 'How can I skip?', 'क्यों बच्चे कूदते हैं?'):
        assert should_consult_first_day_qwen(title, spoken) is True, spoken
    assert should_consult_first_day_qwen('unapproved Class 6 scene', 'why?') is False

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
        'studentMessage': 'Why do bunnies skip?',
        'preferredExplanationLanguage': 'English',
    })
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result['message'].startswith('You told me jump!')
    assert result['modelSentence'] == 'I can skip.'
    assert result['shouldRetry'] is True
    assert result['activityComplete'] is False
    assert calls == [('en', 'Skip like a bunny', 'Why do bunnies skip?', True)]

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


def test_recording_regression_poem_pair_three_never_becomes_at_word_drill(monkeypatch):
    """Video 2026-11-09: highlighted grin/bell but Miss Julie said 'say at'."""
    import asyncio
    from server.compat import BrainRequest
    from server.class1 import respond_class1
    from server.class1_response_guard import guard_class1_response
    import server.class1 as module

    async def no_qwen_for_routine(*args, **kwargs):
        raise AssertionError('A simple pair repeat must not wait for Ollama')

    monkeypatch.setattr(module, 'first_day_qwen_coach', no_qwen_for_routine)
    req = BrainRequest(
        grade=1, levelId='g01-l01',
        sceneKey='poem-pair-3', activityTitle='STALE UNRELATED TITLE',
        currentQuestion='Say the word at.',
        studentMessage='At at.', preferredExplanationLanguage='English',
    )
    result = guard_class1_response(asyncio.run(respond_class1(req)), req)
    assert result['responseQuality'] == 'PARTIAL'
    assert result['shouldRetry'] is True
    assert result['modelSentence'] == 'See me grin. When the bell rings, I go in.'
    assert 'grin' in result['message'].lower()
    assert 'bell' in result['followUpQuestion'].lower()
    assert 'can you say at' not in str(result).lower()
    assert result['activityComplete'] is False
    assert result['memoryUpdates'] == []

    # A genuine two-line attempt is recognized without the legacy short-word
    # guard rewriting it to 'at' simply because the old prompt is stale.
    req.studentMessage = 'See me grin. When the bell rings, I go in.'
    complete = guard_class1_response(asyncio.run(respond_class1(req)), req)
    assert complete['responseQuality'] == 'ADEQUATE'
    assert complete['shouldRetry'] is False
    assert complete['activityComplete'] is False  # Node is sole authority


def test_poem_marathi_hindi_support_stays_on_both_english_lines_without_qwen(monkeypatch):
    import asyncio
    from server.compat import BrainRequest
    from server.class1 import respond_class1
    from server.class1_response_guard import guard_class1_response
    import server.class1 as module

    async def no_qwen(*args, **kwargs):
        raise AssertionError('Known help requests must use the reviewed fast path')
    monkeypatch.setattr(module, 'first_day_qwen_coach', no_qwen)
    for student, preference, native_phrase in [
        ('मला समजत नाही', 'Marathi', 'हसू'),
        ('हिंदी में समझाओ', 'Hindi', 'मुस्कान'),
    ]:
        req = BrainRequest(
            grade=1, levelId='g01-l01', sceneKey='poem-pair-3',
            activityTitle='Poem lines 5–6: grin and bell',
            currentQuestion='Say the word at.', studentMessage=student,
            preferredExplanationLanguage=preference,
        )
        answer = guard_class1_response(asyncio.run(respond_class1(req)), req)
        assert native_phrase in (answer['message'] + answer['followUpQuestion'])
        assert 'See me grin' in answer['modelSentence']
        assert 'bell' in answer['followUpQuestion'].lower()
        assert answer['responseQuality'] == 'UNCLEAR'
        assert answer['activityComplete'] is False


def test_unknown_or_unrecognized_poem_scene_fails_closed_instead_of_at():
    import asyncio
    import pytest
    from fastapi import HTTPException
    from server.compat import BrainRequest
    from server.class1 import respond_class1

    for scene_key, title in [('poem-pair-99', 'Poem lines 99'),
                             ('', 'Poem unknown chapter')]:
        req = BrainRequest(
            grade=1, levelId='g01-l01', sceneKey=scene_key,
            activityTitle=title, currentQuestion='Say the word at.',
            studentMessage='at',
        )
        with pytest.raises(HTTPException) as failure:
            asyncio.run(respond_class1(req))
        assert failure.value.status_code == 422


def test_real_brain_route_cannot_replace_authenticated_poem_with_foundations(monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import app
    monkeypatch.setenv('TALKORA_ENV', 'test')
    monkeypatch.setenv('TALKORA_CLASS1_QWEN_PILOT', 'true')
    client = TestClient(app)
    reply = client.post('/v1/brain/respond', json={
        'grade': 1, 'levelId': 'g01-l01',
        'sceneKey': 'poem-pair-3',
        'activityTitle': 'MISMATCHED OLD TITLE',
        'currentQuestion': 'Say the word at.',
        'studentMessage': 'At at.',
        'preferredExplanationLanguage': 'English',
    })
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data['modelSentence'] == 'See me grin. When the bell rings, I go in.'
    assert 'Can you say at?' not in data['message'] + str(data['followUpQuestion'])
    assert data['activityComplete'] is False
