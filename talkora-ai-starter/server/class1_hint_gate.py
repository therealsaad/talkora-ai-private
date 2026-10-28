"""Fail-closed model-hint gate for the EXISTING Class 1 Level 1 Qwen bridge.

Only teacher-approved, short English hints may supplement the authored lesson.
The current V2 bilingual model did not pass QA, so hi/mr are deliberately
blocked. This module does not grade, store progress, or own any AI route.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any

from .class1_adaptive import APPROVED_WORDS


_BLOCKED_CLAIMS = re.compile(
    r"https?://|www\.|\b(?:phone|address|password|secret|"
    r"pronunciation|pronounced|correctly|accent|score|grade|perfect|flawless|wrong|correct|incorrect|"
    r"noun|verb|adjective|phoneme|syllable)\b|"
    r"\b(?:what is your name|tell me your name|i can see your)\b",
    flags=re.IGNORECASE,
)


def validate_model_hint(raw: Any, *, target: str | None,
                        language: str, mode: str) -> str:
    """Return one safe candidate hint, or empty string for existing baseline.

    Passing these checks does not establish teaching quality; educator approval
    is a separate requirement. Model hints cannot alter progress or actions.
    """
    if target not in APPROVED_WORDS or language != "en":
        return ""
    if mode not in {"MODEL", "GUIDE", "PRACTISE", "EXTEND"}:
        return ""
    if not isinstance(raw, str) or len(raw) > 1024:
        return ""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if (not isinstance(payload, dict) or set(payload) != {"hint"}
            or not isinstance(payload["hint"], str)):
        return ""
    hint = unicodedata.normalize("NFKC", payload["hint"]).strip()
    if not hint or len(hint) > 130 or not 2 <= len(hint.split()) <= 12:
        return ""
    if re.search(r"[\u0900-\u097f]", hint) or _BLOCKED_CLAIMS.search(hint):
        return ""
    if not re.search(r"\b" + re.escape(target) + r"\b", hint, re.IGNORECASE):
        return ""
    tokens = re.findall(r"\w+", hint.casefold(), flags=re.UNICODE)
    if len(tokens) >= 5 and any(count >= 4 for count in Counter(tokens).values()):
        return ""
    if mode in ("PRACTISE", "EXTEND") and re.search(
        r"\b(?:try again|not correct|say it again|wrong answer)\b", hint,
        flags=re.IGNORECASE,
    ):
        return ""
    return hint
