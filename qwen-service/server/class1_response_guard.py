"""Response-only guard for Talkora Class 1 pilot; no grading or lesson progression.

Works with the existing /v1/brain/respond handler. KG and other levels are untouched.
"""
from __future__ import annotations

import re
from typing import Any

# Whitelist permits repeat-mode prompts, but not arbitrary pupil content.
WORDS = frozenset(('am', 'an', 'at', 'in', 'is', 'it', 'on', 'up'))


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
        response['followUpQuestion'] = f"Can you say '{target}' once more?"
        # Qwen may supply a grammatical digression after the fixed baseline.
        # Keep the reply deterministic and gentle for this micro-activity.
        quality = response.get('responseQuality')
        if quality == 'PARTIAL':
            response['message'] = f"Good effort! Listen once more, then say '{target}'."
        elif quality == 'UNCLEAR':
            response['message'] = f"Let's listen together. Say '{target}' when you're ready."
        else:
            response['message'] = f"I heard '{target}'. Nice effort! Let's say it together once more."
        response['activityComplete'] = False
        response['memoryUpdates'] = []
        response['detectedSkills'] = []
        response['remainingSkills'] = []
    return response
