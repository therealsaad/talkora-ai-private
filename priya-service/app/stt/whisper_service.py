import asyncio
import logging
import time
from pathlib import Path

from ..config import settings
from ..inference_runtime import gpu_inference_lock
from ..model_cache import local_huggingface_snapshot


logger = logging.getLogger('talkora.stt')


class STTError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WhisperService:
    def __init__(self) -> None:
        self._model = None
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def model_repo(self) -> str:
        return f'Systran/faster-whisper-{settings.stt_model}'

    @property
    def model_available(self) -> bool:
        return local_huggingface_snapshot(self.model_repo) is not None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTError('STT_DEPENDENCY_MISSING', 'Speech recognition is not installed.') from exc

            model_source = local_huggingface_snapshot(self.model_repo)
            if model_source is None:
                raise STTError('STT_MODEL_MISSING', 'The speech recognition model is not provisioned.')

            started = time.perf_counter()
            logger.info('Loading Whisper model=%s device=%s compute_type=%s', settings.stt_model, settings.stt_device, settings.stt_compute_type)
            try:
                self._model = WhisperModel(
                    str(model_source),
                    device=settings.stt_device,
                    compute_type=settings.stt_compute_type,
                )
            except Exception as exc:
                logger.exception('Whisper model load failed')
                raise STTError('STT_MODEL_LOAD_FAILED', 'Speech recognition could not start.') from exc
            logger.info(
                'Whisper loaded once device=%s latency_ms=%d',
                settings.stt_device,
                round((time.perf_counter() - started) * 1000),
            )

    def _transcribe_sync(self, path: Path) -> dict:
        self._load()
        segments, info = self._model.transcribe(
            str(path),
            language='en',
            beam_size=3,
            vad_filter=True,
            word_timestamps=True,
        )
        collected = list(segments)
        text = ' '.join(segment.text.strip() for segment in collected).strip()
        words = [
            word.word.strip()
            for segment in collected
            for word in (segment.words or [])
        ]
        duration = max((segment.end for segment in collected), default=0)
        return {
            'text': text,
            'transcript': text,
            'words': words,
            'durationSeconds': duration,
            'language': info.language,
            'confidence': info.language_probability,
            'provider': 'faster-whisper',
            'model': settings.stt_model,
        }

    async def transcribe(self, path: Path) -> dict:
        if not self.available:
            raise RuntimeError('faster-whisper is not installed in the AI service environment.')

        started = time.perf_counter()
        async with self._lock:
            # CPU Whisper does not compete for Priya's CUDA memory, so it must
            # not wait behind the TTS GPU inference lock.
            try:
                if settings.stt_device.lower().startswith('cuda'):
                    async with gpu_inference_lock:
                        result = await asyncio.to_thread(self._transcribe_sync, path)
                else:
                    result = await asyncio.to_thread(self._transcribe_sync, path)
            except Exception as exc:
                if exc.__class__.__name__ == 'InvalidDataError' or 'invalid data' in str(exc).lower():
                    raise ValueError('The uploaded audio format could not be decoded.') from exc
                logger.exception('Whisper transcription failed path_suffix=%s', path.suffix)
                if isinstance(exc, STTError):
                    raise
                raise STTError('STT_INFERENCE_FAILED', 'Speech recognition failed for this recording.') from exc

        result['latencyMs'] = round((time.perf_counter() - started) * 1000)
        logger.info(
            'STT latency_ms=%d duration_seconds=%.2f',
            result['latencyMs'],
            result['durationSeconds'],
        )
        return result


whisper_service = WhisperService()
