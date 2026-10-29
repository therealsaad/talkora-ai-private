"""Response-only guard for Talkora Class 1 pilot; no grading or lesson progression.

Works with the existing /v1/brain/respond handler. KG and other levels are untouched.
"""
from __future__ import annotations

import re
from typing import Any

# Whitelist permits repeat-mode prompts, but not arbitrary pupil content.
from .class1_adaptive import APPROVED_WORDS
from .class1_language import resolve_support_language

WORDS = APPROVED_WORDS


def _target(req: Any) -> str | None:
    # Reuse the installed Class 1 lesson target matcher; it may have local changes.
    from .class1 import active_target

    target = active_target(
        str(getattr(req, 'currentQuestion', '') or ''),
        str(getattr(req, 'activityTitle', '') or ''),
    )
    return target if target in WORDS else None


def _repeat_mode(req: Any) -> bool:
    prompt = ' '.join((
        str(getattr(req, 'currentQuestion', '') or ''),
        str(getattr(req, 'activityTitle', '') or ''),
    )).lower()
    return bool(re.search(r'\b(?:listen\s+and\s+repeat|say\s+the\s+word|repeat\s+the\s+word)\b', prompt))


def guard_class1_response(result: dict[str, Any], req: Any) -> dict[str, Any]:
    """Polish audio-safe wording; do not change scores or student records."""
    if not isinstance(result, dict):
        return result
    response = dict(result)
    message = response.get('message')
    if isinstance(message, str):
        message = re.sub(r'(?<=[.!?])(?=[A-Za-z])', ' ', message.strip())
        message = re.sub(r'[ \t]+', ' ', message)
        response['message'] = message
    target = _target(req)
    if _repeat_mode(req) and target:
        # A learner asked to repeat one short word should not suddenly be
        # evaluated on sentence-building or preposition grammar.
        language = resolve_support_language(
            str(getattr(req, 'preferredExplanationLanguage', 'English')),
            str(getattr(req, 'studentMessage', '')),
        ) or 'en'
        follow_ups = {
            'en': f"Can you say '{target}' once more?",
            'hi': f"क्या तुम {target} एक बार और बोलोगे?",
            'mr': f"{target} पुन्हा एकदा म्हणशील का?",
        }
        response['followUpQuestion'] = follow_ups[language]
        # Qwen may supply a grammatical digression after the fixed baseline.
        # Keep the reply deterministic and gentle for this micro-activity.
        quality = response.get('responseQuality')
        phrases = {
            'en': {
                'PARTIAL': f"Good effort! Listen once more, then say '{target}'.",
                'UNCLEAR': f"Let's listen together. Say '{target}' when you're ready.",
                'ADEQUATE': f"I heard '{target}'. Nice effort! Let's say it together once more.",
            },
            'hi': {
                'PARTIAL': f"अच्छी कोशिश! सुनो: {target}। अब साथ में बोलो।",
                'UNCLEAR': f"ध्यान से सुनो: {target}। तैयार हो तो बोलो।",
                'ADEQUATE': f"मैंने {target} सुना। बहुत अच्छी कोशिश! फिर बोलो।",
            },
            'mr': {
                'PARTIAL': f"छान प्रयत्न! ऐक: {target}. आता एकत्र म्हणू.",
                'UNCLEAR': f"नीट ऐक: {target}. तयार झाल्यावर म्हण.",
                'ADEQUATE': f"मला {target} ऐकू आलं. छान प्रयत्न! पुन्हा म्हण.",
            },
        }
        response['message'] = phrases[language].get(
            quality, phrases[language]['ADEQUATE']
        )
        response['activityComplete'] = False
        response['memoryUpdates'] = []
        response['detectedSkills'] = []
        response['remainingSkills'] = []
    return response
