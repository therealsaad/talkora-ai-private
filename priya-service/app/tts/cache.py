import hashlib
import json
import logging
import unicodedata
import wave
from pathlib import Path

from ..config import settings
from .text_cleaner import clean_tts_text


logger = logging.getLogger('talkora.tts.cache')
MINIMUM_WAV_BYTES = 1_024
SUPPORTED_LANGUAGE_ALIASES = {'en': 'en-IN', 'en-in': 'en-IN', 'en_in': 'en-IN'}


def normalize_cache_text(text: str) -> str:
    cleaned = clean_tts_text(unicodedata.normalize('NFKC', str(text or '')))
    return cleaned.casefold().rstrip('.,').strip()


def normalize_tts_language(language: str | None) -> str:
    raw = str(language or settings.tts_language or 'en-IN').strip()
    return SUPPORTED_LANGUAGE_ALIASES.get(raw.casefold(), raw)


def build_tts_cache_key(text: str, voice: str, language: str, style_version: str, model: str) -> str:
    # Keep the established field order/delimiter so the existing generated
    # curriculum pack remains addressable after this centralization.
    identity = '\n'.join([
        normalize_cache_text(text),
        voice.strip().casefold(),
        normalize_tts_language(language),
        style_version.strip(),
        model.strip(),
    ])
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


cache_key = build_tts_cache_key


def get_tts_cache_path(key: str, voice: str, language: str) -> Path:
    path = settings.storage_root / 'tts' / normalize_tts_language(language) / voice.strip().casefold() / f'{key}.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


audio_path = get_tts_cache_path


def is_valid_cached_audio(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < MINIMUM_WAV_BYTES:
        return False
    try:
        with wave.open(str(path), 'rb') as audio:
            return audio.getnchannels() > 0 and audio.getframerate() > 0 and audio.getnframes() > 0
    except (OSError, EOFError, wave.Error):
        return False


def get_cached_audio(path: Path) -> Path | None:
    if is_valid_cached_audio(path):
        return path
    if path.exists():
        logger.warning('Removing invalid TTS cache file path=%s size=%d', path, path.stat().st_size)
        path.unlink(missing_ok=True)
        metadata_path(path).unlink(missing_ok=True)
    return None


def find_compatible_cached_audio(
    text: str,
    voice_id: str,
    language: str,
    model: str,
) -> tuple[Path, str] | None:
    """Find a valid current-voice WAV left in an older cache directory."""
    cache_root = settings.storage_root / 'tts' / normalize_tts_language(language)
    if not cache_root.is_dir():
        return None

    normalized_text = normalize_cache_text(text)
    expected_voice = voice_id.strip().casefold()
    expected_model = model.strip().casefold()

    for metadata in sorted(cache_root.glob('*/*.json')):
        try:
            payload = json.loads(metadata.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

        if normalize_cache_text(payload.get('text', '')) != normalized_text:
            continue
        if str(payload.get('voiceId', '')).strip().casefold() != expected_voice:
            continue
        if str(payload.get('model', '')).strip().casefold() != expected_model:
            continue
        if normalize_tts_language(payload.get('language')) != normalize_tts_language(language):
            continue

        audio = metadata.with_suffix('.wav')
        if get_cached_audio(audio):
            return audio, str(payload.get('audioHash') or audio.stem)

    return None


def metadata_path(audio: Path) -> Path:
    return audio.with_suffix('.json')


def write_metadata(audio: Path, metadata: dict) -> None:
    target = metadata_path(audio)
    temporary = target.with_suffix('.json.part')
    temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(target)
