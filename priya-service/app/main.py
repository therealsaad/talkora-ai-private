import asyncio
import inspect
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .brain.qwen_client import QwenUnavailable, qwen_client
from .brain.schemas import BrainRequest
from .config import settings
from .pronunciation.evaluator import PronunciationRequest, evaluate_speech
from .stt.whisper_service import whisper_service
from .tts.parler_service import parler_service as tts_service

try:
    import torch
except ImportError:  # pragma: no cover - the production voice environment includes torch
    torch = None  # type: ignore[assignment]

# -----------------------------------------------------------------------------
# Backward-compatible optional imports
# -----------------------------------------------------------------------------
# Your newer local branch may already contain these helpers, while the older
# uploaded AI-services ZIP did not. Keeping fallbacks here means this main.py can
# run against either version without deleting/changing the existing lesson cache.

try:
    from .stt.whisper_service import STTError  # type: ignore
except ImportError:
    class STTError(RuntimeError):
        code = 'STT_FAILED'


try:
    from .tts.cache import normalize_tts_language  # type: ignore
except ImportError:
    def normalize_tts_language(value: str | None) -> str:
        normalized = (value or 'en-IN').strip()
        aliases = {
            'en': 'en-IN',
            'en-in': 'en-IN',
            'en_in': 'en-IN',
            'english': 'en-IN',
        }
        return aliases.get(normalized.lower(), normalized)


try:
    from .tts.voice_profiles import (
        PRIYA_STYLE_VERSION,
        PRIYA_VOICE_ID,
        PRIYA_VOICE_NAME,
        normalize_priya_voice,
    )
except ImportError:
    from .tts.voice_profiles import PRIYA_STYLE_VERSION

    PRIYA_VOICE_NAME = str(getattr(settings, 'tts_voice', 'Priya'))
    PRIYA_VOICE_ID = str(
        getattr(settings, 'tts_style_version', PRIYA_STYLE_VERSION)
        or PRIYA_STYLE_VERSION
    )

    def normalize_priya_voice(value: str | None) -> str:
        candidate = (value or PRIYA_VOICE_ID).strip()
        accepted = {
            PRIYA_VOICE_ID.lower(),
            PRIYA_VOICE_NAME.lower(),
            'priya',
            'talkora-priya-v2',
        }
        if candidate.lower() not in accepted:
            raise ValueError(
                f'Unsupported Miss Julie voice "{candidate}". '
                f'Use "{PRIYA_VOICE_ID}" or "{PRIYA_VOICE_NAME}".'
            )
        return PRIYA_VOICE_ID


try:
    from .curriculum.voice_prewarm import curriculum_voice_prewarmer  # type: ignore
except ImportError:
    curriculum_voice_prewarmer = None


logger = logging.getLogger('talkora.api')


# -----------------------------------------------------------------------------
# Compatibility wrappers
# -----------------------------------------------------------------------------
async def _synthesize_priya(text: str, voice: str, language: str):
    """Call either the old or new cached Priya service signature safely.

    Old service:
        synthesize(text)

    New service:
        synthesize(text, voice=..., language=...)

    We inspect the signature instead of catching TypeError from inside the model,
    so a real synthesis error is never accidentally hidden/retried.
    """
    parameters = inspect.signature(tts_service.synthesize).parameters
    kwargs: dict[str, str] = {}

    if 'voice' in parameters:
        kwargs['voice'] = voice
    if 'language' in parameters:
        kwargs['language'] = language

    return await tts_service.synthesize(text, **kwargs)


class _InlineVoicePrewarmer:
    """Fallback prewarmer used only when curriculum.voice_prewarm is absent.

    It uses the existing content-addressed Priya cache. Cache hits are reused;
    this class never deletes or overwrites the existing lesson cache.
    """

    def __init__(self) -> None:
        self.pending = 0
        self.generated = 0
        self.failed = 0
        self._tasks: set[asyncio.Task] = set()

    async def _run(self, texts: list[str]) -> None:
        try:
            for text in texts:
                try:
                    result = await _synthesize_priya(
                        text,
                        voice=PRIYA_VOICE_ID,
                        language='en-IN',
                    )
                    if not bool(getattr(result, 'cached', False)):
                        self.generated += 1
                except Exception:
                    self.failed += 1
                    logger.exception('Background TTS prewarm failed text=%r', text[:120])
                finally:
                    self.pending = max(0, self.pending - 1)
        except asyncio.CancelledError:
            raise

    def enqueue(self, texts: list[str]) -> int:
        cleaned: list[str] = []
        seen: set[str] = set()

        for raw in texts:
            text = raw.strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        if not cleaned:
            return 0

        self.pending += len(cleaned)
        task = asyncio.create_task(self._run(cleaned))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return len(cleaned)

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


_inline_voice_prewarmer = _InlineVoicePrewarmer()


def _voice_prewarmer():
    return curriculum_voice_prewarmer or _inline_voice_prewarmer


# -----------------------------------------------------------------------------
# FastAPI app + lifecycle
# -----------------------------------------------------------------------------
_tts_warmup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm the local Priya lesson voice without blocking startup and cleanly stop tasks."""
    global _tts_warmup_task

    warm_on_startup = bool(getattr(settings, 'tts_warm_on_startup', False))
    if warm_on_startup and tts_service.model_available:
        _tts_warmup_task = asyncio.create_task(tts_service.warm_up())

    try:
        yield
    finally:
        if _tts_warmup_task and not _tts_warmup_task.done():
            _tts_warmup_task.cancel()
            await asyncio.gather(_tts_warmup_task, return_exceptions=True)
        _tts_warmup_task = None

        if curriculum_voice_prewarmer is None:
            await _inline_voice_prewarmer.shutdown()


app = FastAPI(
    title='Talkora Internal AI Service',
    version='1.3.0',
    docs_url='/docs',
    lifespan=lifespan,
)


# -----------------------------------------------------------------------------
# Error responses
# -----------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else None
    code = detail.get('code') if detail else (
        'INVALID_AUDIO' if exc.status_code == 400 else 'AI_SERVICE_ERROR'
    )
    message = detail.get('message') if detail else str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            'success': False,
            'error': {
                'code': code,
                'message': message,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'Request validation failed',
                'details': exc.errors(),
            },
        },
    )


# -----------------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------------
class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    voice: str = PRIYA_VOICE_ID
    language: str = 'en-IN'

    @field_validator('voice', mode='before')
    @classmethod
    def normalize_voice(cls, value: object) -> str:
        try:
            return normalize_priya_voice(None if value is None else str(value))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator('language', mode='before')
    @classmethod
    def normalize_language(cls, value: object) -> str:
        language = normalize_tts_language(None if value is None else str(value))
        if language != 'en-IN':
            raise ValueError('Miss Julie cached lesson TTS currently supports en-IN speech only.')
        return language


class TTSPrewarmRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=500)
    voice: str = PRIYA_VOICE_ID
    language: str = 'en-IN'

    @field_validator('voice', mode='before')
    @classmethod
    def normalize_voice(cls, value: object) -> str:
        try:
            return normalize_priya_voice(None if value is None else str(value))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator('language', mode='before')
    @classmethod
    def normalize_language(cls, value: object) -> str:
        language = normalize_tts_language(None if value is None else str(value))
        if language != 'en-IN':
            raise ValueError('Miss Julie lesson TTS prewarm supports en-IN only.')
        return language


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get('/health')
async def health():
    try:
        cuda = bool(torch is not None and torch.cuda.is_available())
        gpu_name = torch.cuda.get_device_name(0) if cuda and torch is not None else None
    except Exception as exc:
        logger.warning('PyTorch runtime unavailable during health check: %s', exc)
        cuda = False
        gpu_name = None

    try:
        qwen = await qwen_client.status()
    except Exception as exc:
        logger.warning('Qwen health check failed: %s', exc)
        qwen = {
            'reachable': False,
            'modelAvailable': False,
        }

    tts_device = str(getattr(settings, 'tts_device', 'cpu'))
    local_stt_available = bool(
        whisper_service.available and whisper_service.model_available
    )

    # The Node/Railway backend can use Groq STT directly. Local Whisper remains
    # available here only as a compatibility/fallback endpoint, so it is reported
    # but not required for this AI-service health status.
    components_ready = [
        bool(qwen.get('reachable')),
        bool(qwen.get('modelAvailable')),
        bool(tts_service.available),
        bool(tts_service.model_available),
        tts_service.status in {'ready', 'lazy-ready'},
    ]

    if tts_device.startswith('cuda'):
        components_ready.append(cuda)

    prewarmer = _voice_prewarmer()

    return {
        'status': 'ok' if all(components_ready) else 'degraded',
        'version': app.version,
        'ollamaReachable': bool(qwen.get('reachable')),
        'qwenAvailable': bool(qwen.get('modelAvailable')),
        'qwenModel': getattr(settings, 'ollama_model', None),
        'qwenNumGpu': getattr(settings, 'ollama_num_gpu', None),
        'parlerImport': tts_service.available,
        'ttsModelAvailable': tts_service.model_available,
        'ttsProvider': tts_service.name,
        'ttsModelLoaded': tts_service.loaded,
        'ttsReady': tts_service.status in {'ready', 'lazy-ready'},
        'ttsStatus': tts_service.status,
        'ttsDevice': tts_service.device,
        'ttsModelLoadLatencyMs': tts_service.load_latency_ms,
        'ttsLatestTimings': tts_service.latest_timings,
        'ttsVoice': PRIYA_VOICE_NAME,
        'ttsVoiceId': PRIYA_VOICE_ID,
        'ttsStyleVersion': PRIYA_STYLE_VERSION,
        'ttsPrewarmPending': int(getattr(prewarmer, 'pending', 0)),
        'ttsPrewarmGenerated': int(getattr(prewarmer, 'generated', 0)),
        'ttsPrewarmFailed': int(getattr(prewarmer, 'failed', 0)),
        'sttRole': 'local-fallback',
        'sttAvailable': local_stt_available,
        'sttModelLoaded': whisper_service.loaded,
        'sttDevice': getattr(settings, 'stt_device', None),
        'cuda': cuda,
        'gpu': gpu_name,
    }


# -----------------------------------------------------------------------------
# Brain / Qwen
# -----------------------------------------------------------------------------
@app.post('/v1/brain/respond')
async def brain_respond(request: BrainRequest):
    try:
        return await qwen_client.respond(request)
    except QwenUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                'code': 'QWEN_UNAVAILABLE',
                'message': str(exc),
            },
        ) from exc


# -----------------------------------------------------------------------------
# Cached Priya / Indic-Parler lesson TTS
# -----------------------------------------------------------------------------
@app.post('/v1/tts')
async def tts(request: TTSRequest):
    try:
        result = await _synthesize_priya(
            request.text,
            voice=request.voice,
            language=request.language,
        )

        return FileResponse(
            result.path,
            media_type='audio/wav',
            filename=Path(result.path).name,
            headers={
                'X-Talkora-Audio-Hash': result.audio_hash,
                'X-Talkora-Cache': 'HIT' if result.cached else 'MISS',
                'X-Talkora-Cache-Key': result.audio_hash[:12],
                'X-Talkora-TTS-Source': 'PREGENERATED' if result.cached else 'GENERATED',
                'X-Talkora-TTS-Latency-Ms': str(result.latency_ms),
                'X-Talkora-Audio-Duration-Seconds': f'{result.duration_seconds:.3f}',
                'X-Talkora-Voice': PRIYA_VOICE_NAME,
                'X-Talkora-Voice-Id': PRIYA_VOICE_ID,
                'X-Talkora-TTS-Phases': ','.join(
                    f'{key}={value}' for key, value in result.timings.items()
                ),
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={'code': 'INVALID_TTS_REQUEST', 'message': str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={'code': 'TTS_UNAVAILABLE', 'message': str(exc)},
        ) from exc


# -----------------------------------------------------------------------------
# Login-time/cache prewarm
# -----------------------------------------------------------------------------
async def _queue_tts_prewarm(request: TTSPrewarmRequest):
    """Queue only missing/cacheable English lesson/personalized lines.

    IMPORTANT:
    - This does not delete any existing WAV/metadata.
    - Existing content-addressed cache entries remain cache HITs.
    - The request returns immediately after queuing work.
    - Dynamic conversation audio is NOT generated here; Node routes it to Groq TTS.
    """
    prewarmer = _voice_prewarmer()
    accepted = prewarmer.enqueue(request.texts)

    return {
        'accepted': accepted,
        'pending': int(getattr(prewarmer, 'pending', 0)),
        'voice': PRIYA_VOICE_NAME,
        'voiceId': PRIYA_VOICE_ID,
        'language': request.language,
        'cachePolicy': 'reuse-existing-generate-missing-only',
    }


@app.post('/v1/tts/prewarm', status_code=status.HTTP_202_ACCEPTED)
async def tts_prewarm(request: TTSPrewarmRequest):
    """Canonical newer endpoint."""
    return await _queue_tts_prewarm(request)


@app.post('/v1/tts/warmup', status_code=status.HTTP_202_ACCEPTED)
async def tts_warmup_compat(request: TTSPrewarmRequest):
    """Backward-compatible alias used by the Railway VoiceWarmupService."""
    return await _queue_tts_prewarm(request)


# -----------------------------------------------------------------------------
# Local STT compatibility/fallback
# -----------------------------------------------------------------------------
# Production Talkora should use SPEECH_PROVIDER=groq in the Node/Railway backend.
# This endpoint is intentionally kept so old/local flows do not break.
@app.post('/v1/stt')
async def stt(audio: UploadFile = File(...)):
    suffixes = {
        'audio/webm': '.webm',
        'audio/ogg': '.ogg',
        'audio/wav': '.wav',
        'audio/x-wav': '.wav',
        'audio/mpeg': '.mp3',
        'audio/mp4': '.m4a',
    }

    mime_type = (audio.content_type or '').split(';', 1)[0].lower()
    suffix = suffixes.get(
        mime_type,
        Path(audio.filename or 'speech.webm').suffix or '.webm',
    )

    payload = await audio.read()
    logger.info(
        '[STT] received mime=%s bytes=%d filename=%s',
        mime_type,
        len(payload),
        audio.filename or 'speech.webm',
    )

    if not payload:
        raise HTTPException(
            status_code=400,
            detail={
                'code': 'EMPTY_AUDIO',
                'message': 'The uploaded audio is empty.',
            },
        )

    if len(payload) > 8_000_000:
        raise HTTPException(
            status_code=413,
            detail={
                'code': 'AUDIO_TOO_LARGE',
                'message': 'The uploaded audio exceeds the 8 MB limit.',
            },
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as target:
        target.write(payload)
        path = Path(target.name)

    try:
        return await whisper_service.transcribe(path)
    except STTError as exc:
        code = getattr(exc, 'code', 'STT_FAILED')
        logger.error('[STT] failed code=%s reason=%s', code, exc)
        raise HTTPException(
            status_code=503,
            detail={'code': code, 'message': str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={'code': 'INVALID_AUDIO', 'message': str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={'code': 'STT_UNAVAILABLE', 'message': str(exc)},
        ) from exc
    finally:
        path.unlink(missing_ok=True)


# -----------------------------------------------------------------------------
# Pronunciation evaluation
# -----------------------------------------------------------------------------
@app.post('/v1/pronunciation/evaluate')
async def pronunciation(request: PronunciationRequest):
    return evaluate_speech(request)
