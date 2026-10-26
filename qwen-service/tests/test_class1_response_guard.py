from types import SimpleNamespace

from server.class1_response_guard import guard_class1_response


def req(q='Say the word at.', title='Listen and repeat at'):
    return SimpleNamespace(currentQuestion=q, activityTitle=title)


def test_repeat_is_not_sentence_building():
    d = {'message': 'I heard the word at.Nice effort! Use at near the table.',
         'followUpQuestion': 'Can you useat in a little sentence?',
         'responseQuality': 'ADEQUATE', 'activityComplete': True,
         'memoryUpdates': [{'x': 'y'}], 'detectedSkills': ['phonics']}
    result = guard_class1_response(d, req())
    assert result['message'] == "I heard 'at'. Nice effort! Let's say it together once more."
    assert result['followUpQuestion'] == "Can you say 'at' once more?"
    assert result['responseQuality'] == 'ADEQUATE'
    assert result['activityComplete'] is False
    assert result['memoryUpdates'] == []
    assert result['detectedSkills'] == []
    assert d['activityComplete'] is True  # non-mutating


def test_wrong_word_not_praised_as_observed():
    d = {'message': 'Keep going.', 'responseQuality': 'PARTIAL'}
    result = guard_class1_response(d, req())
    assert result['message'].startswith('Good effort!')
    assert "'at'" in result['followUpQuestion']


def test_sentence_building_not_forced_into_repeat_mode():
    d = {'message': 'Great.Try it.', 'followUpQuestion': 'What next?',
         'responseQuality': 'ADEQUATE'}
    result = guard_class1_response(d, req('Build a sentence.', 'Put these words in order: I / am / Sam.'))
    assert result['message'] == 'Great. Try it.'
    assert result['followUpQuestion'] == 'What next?'


def test_unrecognized_teacher_prompt_does_not_guess_pupil_target():
    d = {'message': 'Nice.Try again.', 'responseQuality': 'UNCLEAR'}
    result = guard_class1_response(d, req('Say the word you heard.', 'Listen and repeat'))
    assert result['message'] == 'Nice. Try again.'
