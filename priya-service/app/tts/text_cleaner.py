import re
import unicodedata


_LABEL_PREFIX = re.compile(
    r'^\s*(?:correction|explanation|answer|hint|feedback|teacher|miss julie)\s*:\s*',
    flags=re.IGNORECASE,
)


def clean_tts_text(text: str) -> str:
    """Convert UI/LLM text into natural spoken text for Priya.

    This deliberately removes presentation markup without rewriting the learner's
    actual English content. Cache keys use the same normalized text.
    """
    value = unicodedata.normalize('NFKC', str(text or ''))

    # Fenced/code-like presentation does not belong in speech.
    value = re.sub(r'```.*?```', ' ', value, flags=re.S)

    # Remove markdown link syntax but keep the visible label.
    value = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', value)

    # Remove common markdown formatting characters.
    value = re.sub(r'[*_#>`~{}|]', ' ', value)

    # Drop emoji/symbol planes that often make a TTS model sound unnatural.
    value = re.sub(r'[\u2600-\u27bf\u2b00-\u2bff\U00010000-\U0010ffff]', '', value)

    # Remove bullet prefixes and UI labels line-by-line.
    cleaned_lines: list[str] = []
    for line in value.splitlines():
        line = re.sub(r'^\s*(?:[-•]+|\d+[.)])\s*', '', line)
        line = _LABEL_PREFIX.sub('', line)
        if line.strip():
            cleaned_lines.append(line.strip())
    value = ' '.join(cleaned_lines)

    # Normalise expressive spellings/punctuation that hurt natural delivery.
    value = re.sub(r'([!?.,])\1+', r'\1', value)
    value = re.sub(r'\.{2,}', '.', value)
    value = re.sub(r'\b(Aha|Ooh|Yes)(?:a|h|s){2,}\b', r'\1', value, flags=re.IGNORECASE)

    # Normalise whitespace only; do not paraphrase the actual sentence.
    return re.sub(r'\s+', ' ', value).strip()
