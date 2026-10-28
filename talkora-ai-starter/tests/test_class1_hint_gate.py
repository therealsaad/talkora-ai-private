"""Reject the precise Class 1 QLoRA failures seen in held-out evaluation."""
import json

from server.class1_hint_gate import validate_model_hint


def accept(hint, mode='MODEL'):
    return validate_model_hint(json.dumps({'hint': hint}), target='am', language='en', mode=mode)


def test_safe_short_teacher_example():
    assert accept('Listen: am. Say am with me.') == 'Listen: am. Say am with me.'


def test_rejects_non_json_and_extra_fields():
    assert validate_model_hint('not json', target='am', language='en', mode='MODEL') == ''
    assert validate_model_hint('{"hint":"say am", "score":100}', target='am', language='en', mode='MODEL') == ''


def test_rejects_generic_or_repeating_hints():
    assert accept("Let's try again.") == ''  # no target word
    assert accept('am am am am am am am am am am am am') == ''
    assert accept('Say am with me. Now try.', mode='PRACTISE') != ''
    assert accept('Please try again with am.', mode='PRACTISE') == ''


def test_blocks_claims_and_unreviewed_bilingual_mode():
    assert accept('Your pronunciation of am is perfect.') == ''
    assert validate_model_hint('{"hint":"सुनो am बोलो"}', target='am', language='hi', mode='GUIDE') == ''
