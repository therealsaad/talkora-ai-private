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
