"""Canonical Talkora / Miss Julie voice profile.

The public voice id is versioned because it participates in the shared WAV cache.
All old ids are accepted as migration aliases but are normalized to the current id,
so an older client cannot cause FastAPI/Pydantic 422 errors during rollout.
"""
PRIYA_VOICE_NAME = 'Priya'
PRIYA_VOICE_ID = 'talkora-priya-v7-female-teacher'
PRIYA_STYLE_VERSION = PRIYA_VOICE_ID

PRIYA_STYLE = (
    "Mary speaks in a cheerful, expressive, warm female Indian English voice. "
    "Her voice is slightly high-pitched, bright, playful, and friendly. "
    "She speaks like a happy kindergarten teacher teaching four-year-old children. "
    "Her pronunciation is very clear, with gentle pauses and a moderate speaking pace. "
    "Her delivery is animated, encouraging, and natural. "

    "The recording is very high quality, close up, with no background noise."
)

PRIYA_DESCRIPTION = PRIYA_STYLE

# Descriptive alias for code/readability. PRIYA_STYLE remains the compatibility API.
PRIYA_DESCRIPTION = PRIYA_STYLE

PRIYA_VOICE_ALIASES = {
    'Priya': PRIYA_VOICE_ID,
    'priya': PRIYA_VOICE_ID,
    'talkora-priya-v1': PRIYA_VOICE_ID,
    'talkora-priya-v2': PRIYA_VOICE_ID,
    'talkora-priya-v6-indian-kids-teacher': PRIYA_VOICE_ID,
    'talkora-priya-v5-kids-indian': PRIYA_VOICE_ID,
    'talkora-indicf5-miss-julie-v1': PRIYA_VOICE_ID,
    PRIYA_VOICE_ID: PRIYA_VOICE_ID,
}


def normalize_priya_voice(value: str | None) -> str:
    """Return the canonical Miss Julie voice id or raise for an unknown voice."""
    if value is None or not str(value).strip():
        return PRIYA_VOICE_ID

    raw = str(value).strip()
    canonical = PRIYA_VOICE_ALIASES.get(raw)
    if canonical is None:
        raise ValueError(
            f'Unsupported Talkora voice {raw!r}. '
            f'Use Priya or {PRIYA_VOICE_ID}.'
        )
    return canonical
