import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .cache import (
    build_tts_cache_key,
    find_compatible_cached_audio,
    get_cached_audio,
    get_tts_cache_path,
    normalize_tts_language,
    write_metadata,
)
from .text_cleaner import clean_tts_text
from .voice_profiles import (
    PRIYA_STYLE,
    PRIYA_STYLE_VERSION,
    PRIYA_VOICE_ID,
    PRIYA_VOICE_NAME,
    normalize_priya_voice,
)
from ..config import settings
from ..inference_runtime import gpu_inference_lock
from ..model_cache import local_huggingface_snapshot


logger = logging.getLogger('talkora.tts')


@dataclass
class TTSResult:
    path: str
    audio_hash: str
    cached: bool
    text: str
    latency_ms: int
    duration_seconds: float
    timings: dict[str, int]


class ParlerService:
    name = 'python-priya-cache'

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(max(1, settings.tts_concurrency))
        self._model = None
        self._tokenizer = None
        self._description_tokenizer = None
        self._device = 'not-loaded'
        self._load_latency_ms = 0
        self._latest_timings: dict[str, int] = {}
        self._load_lock = threading.Lock()
        self._inflight_locks: dict[str, asyncio.Lock] = {}
        self._loading = False
        self._ready = False

    @property
    def available(self) -> bool:
        try:
            import parler_tts  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def model_available(self) -> bool:
        return (
            local_huggingface_snapshot(settings.tts_model) is not None
            and local_huggingface_snapshot('google/flan-t5-large', ('tokenizer_config.json',)) is not None
        )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def status(self) -> str:
        if self._loading:
            return 'loading'
        if self._ready or self.loaded:
            return 'ready'
        return 'not-loaded'

    @property
    def device(self) -> str:
        return self._device

    @property
    def load_latency_ms(self) -> int:
        return self._load_latency_ms

    @property
    def latest_timings(self) -> dict[str, int]:
        return dict(self._latest_timings)

    def _gpu_memory(self) -> dict[str, int]:
        import torch
        if not torch.cuda.is_available():
            return {'allocatedMb': 0, 'reservedMb': 0}
        return {
            'allocatedMb': round(torch.cuda.memory_allocated() / 1024 / 1024),
            'reservedMb': round(torch.cuda.memory_reserved() / 1024 / 1024),
        }

    def _load(self) -> int:
        with self._load_lock:
            if self._model is not None:
                return 0
            self._loading = True
            try:
                import torch
                from parler_tts import ParlerTTSForConditionalGeneration
                from transformers import AutoTokenizer

                model_source = local_huggingface_snapshot(settings.tts_model)
                if model_source is None:
                    raise RuntimeError(f'Local model snapshot not found for {settings.tts_model}.')
                device = 'cuda:0' if settings.tts_device.startswith('cuda') and torch.cuda.is_available() else 'cpu'
                dtype = torch.float16 if device.startswith('cuda') else torch.float32
                started = time.perf_counter()
                self._model = ParlerTTSForConditionalGeneration.from_pretrained(
                    model_source,
                    local_files_only=True,
                    torch_dtype=dtype,
                    attn_implementation=settings.tts_attention_implementation,
                ).to(device)
                self._tokenizer = AutoTokenizer.from_pretrained(model_source, local_files_only=True)
                description_source = local_huggingface_snapshot(self._model.config.text_encoder._name_or_path, ('tokenizer_config.json',))
                if description_source is None:
                    self._model = None
                    raise RuntimeError('Local google/flan-t5-large tokenizer snapshot not found.')
                self._description_tokenizer = AutoTokenizer.from_pretrained(description_source, local_files_only=True)
                self._device = str(next(self._model.parameters()).device)
                self._load_latency_ms = round((time.perf_counter() - started) * 1000)
                self._ready = True
                logger.info('Parler loaded once device=%s latency_ms=%d gpu=%s', self._device, self._load_latency_ms, self._gpu_memory())
                return self._load_latency_ms
            finally:
                self._loading = False

    async def warm_up(self) -> None:
        """Load Priya off the request path; a cacheable phrase primes first inference."""
        try:
            await asyncio.to_thread(self._load)
            await self.synthesize('Priya is ready.')
            logger.info('Priya startup warm-up complete')
        except Exception:
            logger.exception('Priya startup warm-up failed; text-first fallback remains available')

    def _generate_sync(self, text: str, path: Path) -> tuple[float, dict[str, int]]:
        import numpy as np
        import soundfile as sf
        import torch

        timings: dict[str, int] = {}
        load_ms = self._load()
        timings['modelLoadMs'] = load_ms
        device = next(self._model.parameters()).device
        sample_rate = int(self._model.audio_encoder.config.sampling_rate)

        token_started = time.perf_counter()
        description = self._description_tokenizer(PRIYA_STYLE, return_tensors='pt')
        prompt = self._tokenizer(text, return_tensors='pt')
        timings['tokenizationMs'] = round((time.perf_counter() - token_started) * 1000)

        # Indic Parler can very occasionally return an invalid scalar/near-empty
        # waveform for a short sampled utterance. Never pass that scalar to
        # soundfile: retry the same sentence with a fresh sample instead.
        last_shape: tuple[int, ...] = ()
        generation_total_ms = 0

        for attempt, temperature in enumerate((0.70, 0.76, 0.64), start=1):
            generation_started = time.perf_counter()
            with torch.inference_mode():
                generation = self._model.generate(
                    input_ids=description.input_ids.to(device),
                    attention_mask=description.attention_mask.to(device),
                    prompt_input_ids=prompt.input_ids.to(device),
                    prompt_attention_mask=prompt.attention_mask.to(device),
                    do_sample=True,
                    temperature=temperature,
                )
            generation_total_ms += round((time.perf_counter() - generation_started) * 1000)

            conversion_started = time.perf_counter()
            samples = np.asarray(
                generation.detach().cpu().float().numpy(),
                dtype=np.float32,
            )
            samples = np.squeeze(samples)
            last_shape = tuple(samples.shape)

            # soundfile accepts mono 1-D or frame/channel 2-D data. The model
            # normally returns one mono waveform, so collapse any remaining
            # singleton/batch dimensions. A scalar means generation failed.
            if samples.ndim == 0:
                logger.warning(
                    'Priya produced scalar audio attempt=%d text=%r; retrying',
                    attempt,
                    text[:80],
                )
                continue

            if samples.ndim > 1:
                samples = samples.reshape(-1)

            # Reject tiny malformed outputs rather than writing corrupt WAVs.
            minimum_samples = max(512, int(sample_rate * 0.08))
            if samples.size < minimum_samples:
                logger.warning(
                    'Priya produced too-short audio attempt=%d samples=%d text=%r; retrying',
                    attempt,
                    samples.size,
                    text[:80],
                )
                continue

            if not np.isfinite(samples).all():
                logger.warning(
                    'Priya produced non-finite audio attempt=%d text=%r; retrying',
                    attempt,
                    text[:80],
                )
                continue

            timings['audioConversionMs'] = round((time.perf_counter() - conversion_started) * 1000)
            timings['generationAttempts'] = attempt
            timings['generationMs'] = generation_total_ms

            temporary = path.with_suffix('.part.wav')
            wav_started = time.perf_counter()
            sf.write(temporary, samples, sample_rate, subtype='PCM_16')
            temporary.replace(path)
            timings['wavSerializationMs'] = round((time.perf_counter() - wav_started) * 1000)
            return float(samples.size / sample_rate), timings

        raise RuntimeError(
            f'Priya returned invalid audio after 3 attempts; last_shape={last_shape}.'
        )

    def _unload(self) -> None:
        if self._model is None:
            return
        self._model = None
        self._tokenizer = None
        self._description_tokenizer = None
        self._device = 'not-loaded'
        self._ready = False
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info('Parler released GPU memory for the next Qwen turn')

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
    ) -> TTSResult:
        import soundfile as sf

        started = time.perf_counter()
        request_received = time.perf_counter()
        canonical_voice = normalize_priya_voice(voice or settings.tts_voice)
        canonical_language = normalize_tts_language(language)
        if canonical_language != 'en-IN':
            raise RuntimeError('Miss Julie currently supports en-IN speech only.')
        normalized = clean_tts_text(text)
        normalize_ms = round((time.perf_counter() - request_received) * 1000)
        if not normalized:
            raise RuntimeError('No speakable text was supplied.')
        style_version = (settings.tts_style_version or PRIYA_STYLE_VERSION).strip()
        key = build_tts_cache_key(
            normalized,
            canonical_voice,
            canonical_language,
            style_version,
            settings.tts_model,
        )
        path = get_tts_cache_path(key, canonical_voice, canonical_language)
        cache_lookup_started = time.perf_counter()
        logger.info(
            '[TALKORA TTS] raw=%r normalized=%r voice_input=%r canonical_voice=%s '
            'language=%s model=%s style_version=%s cache_key=%s cache_path=%s cache_exists=%s',
            text, normalized, voice, canonical_voice, canonical_language,
            settings.tts_model, style_version, key, path, path.exists(),
        )
        if get_cached_audio(path):
            duration = float(sf.info(path).duration)
            latency = round((time.perf_counter() - started) * 1000)
            logger.info('TTS cache=HIT latency_ms=%d hash=%s', latency, key[:12])
            timings = {'normalizationMs': normalize_ms, 'cacheLookupMs': round((time.perf_counter() - cache_lookup_started) * 1000), 'totalMs': latency}
            self._latest_timings = timings
            return TTSResult(str(path), key, True, normalized, latency, duration, timings)

        compatible = find_compatible_cached_audio(
            normalized,
            canonical_voice,
            canonical_language,
            settings.tts_model,
        )
        if compatible:
            compatible_path, compatible_hash = compatible
            duration = float(sf.info(compatible_path).duration)
            latency = round((time.perf_counter() - started) * 1000)
            logger.info(
                'TTS cache=HIT compatible_path=true latency_ms=%d hash=%s',
                latency,
                compatible_hash[:12],
            )
            timings = {
                'normalizationMs': normalize_ms,
                'cacheLookupMs': round((time.perf_counter() - cache_lookup_started) * 1000),
                'compatibleCacheHit': 1,
                'totalMs': latency,
            }
            self._latest_timings = timings
            return TTSResult(
                str(compatible_path),
                compatible_hash,
                True,
                normalized,
                latency,
                duration,
                timings,
            )
        cache_lookup_ms = round((time.perf_counter() - cache_lookup_started) * 1000)
        key_lock = self._inflight_locks.setdefault(key, asyncio.Lock())
        async with key_lock:
            if get_cached_audio(path):
                duration = float(sf.info(path).duration)
                latency = round((time.perf_counter() - started) * 1000)
                logger.info('TTS cache=HIT waited_for_inflight=true latency_ms=%d hash=%s', latency, key[:12])
                timings = {'normalizationMs': normalize_ms, 'cacheLookupMs': cache_lookup_ms, 'totalMs': latency}
                self._latest_timings = timings
                return TTSResult(str(path), key, True, normalized, latency, duration, timings)

            availability_started = time.perf_counter()
            if not self.available:
                raise RuntimeError('Indic Parler TTS is not installed in the AI service environment.')
            if not self.model_available:
                raise RuntimeError('The local Indic Parler model cache is incomplete or not visible.')
            availability_ms = round((time.perf_counter() - availability_started) * 1000)

            async with self._semaphore:
                try:
                    async with gpu_inference_lock:
                        duration, phase_timings = await asyncio.to_thread(self._generate_sync, normalized, path)
                except RuntimeError as exc:
                    path.unlink(missing_ok=True)
                    if 'out of memory' in str(exc).lower():
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        raise RuntimeError('Priya voice ran out of GPU memory. Wait for the active inference and try again.') from exc
                    raise
                except Exception as exc:
                    path.unlink(missing_ok=True)
                    raise RuntimeError('Priya could not generate speech from the local model.') from exc
                latency = round((time.perf_counter() - started) * 1000)
                timings = {
                    'normalizationMs': normalize_ms,
                    'cacheLookupMs': cache_lookup_ms,
                    'availabilityCheckMs': availability_ms,
                    **phase_timings,
                    'cacheWriteMs': 0,
                    'totalMs': latency,
                    **{f'gpu{key[0].upper()}{key[1:]}': value for key, value in self._gpu_memory().items()},
                }
                cache_write_started = time.perf_counter()
                write_metadata(path, {
                    'audioHash': key,
                    'text': normalized,
                    'voice': PRIYA_VOICE_NAME,
                    'voiceId': canonical_voice,
                    'language': canonical_language,
                    'model': settings.tts_model,
                    'durationSeconds': duration,
                    'generationLatencyMs': latency,
                    'status': 'ready',
                    'timings': timings,
                })
                timings['cacheWriteMs'] = round((time.perf_counter() - cache_write_started) * 1000)
                self._latest_timings = timings
                logger.info('TTS cache=MISS generation_latency_ms=%d duration_seconds=%.2f hash=%s', latency, duration, key[:12])
                if settings.tts_unload_after_generation:
                    self._unload()
                return TTSResult(str(path), key, False, normalized, latency, duration, timings)


parler_service = ParlerService()
