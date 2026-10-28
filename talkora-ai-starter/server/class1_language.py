"""Conservative language preference for Class 1 English-learning support.

Devanagari alone cannot distinguish Hindi from Marathi. Prefer an explicit
student request, then unmistakable phrases, then the server-provided choice.
Never infer a child's intelligence or identity from their home language.
"""
from __future__ import annotations

import re

LANGUAGES = {"english": "en", "hindi": "hi", "marathi": "mr",
             "en": "en", "hi": "hi", "mr": "mr"}


def resolve_support_language(preference: str, transcript: str) -> str | None:
    default = LANGUAGES.get((preference or "").strip().lower())
    if default is None:
        return None
    speech = (transcript or "")[:300].casefold()
    # Only explicit requests or recognisable language-specific help phrases
    # override the setting. Shared terms like 'क्या/काय' are not enough.
    if re.search(r"मराठीत|मराठीमध्ये|मराठी\s+(?:बोला|बोल|शिकवा)|मला\s+(?:समजत|कळत|समजलं)\s+नाही|"
                 r"\b(?:marathit|marathimadhe|marathi\s+(?:please|mein|madhe)|"
                 r"(?:explain|teach|speak|say)\s+(?:in\s+)?marathi)\b", speech):
        return "mr"
    if re.search(r"हिंदी\s*में|हिन्दी\s*में|हिंदी\s+(?:बोलो|समझाओ)|मुझे\s+समझ\s+नहीं|"
                 r"\b(?:hindime|hindi\s+(?:please|me|mein)|"
                 r"(?:explain|teach|speak|say)\s+(?:in\s+)?hindi)\b", speech):
        return "hi"
    if re.search(r"\b(?:in english|english please)\b|अंग्रेजी\s*में|इंग्लिश\s*में", speech):
        return "en"
    return default
