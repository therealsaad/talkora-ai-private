"""Background fixed-line voice-pack generation.

Known curriculum lines are queued once and written into the same shared Priya WAV
cache that live /v1/tts requests use. The queue is intentionally single-worker:
Talkora's 6 GB laptop target must not run multiple Priya generations in parallel.
"""

import asyncio
import logging
from collections.abc import Iterable

from ..config import settings
from ..tts.parler_service import parler_service
from ..tts.text_cleaner import clean_tts_text


logger = logging.getLogger('talkora.voice_prewarm')


class CurriculumVoicePrewarmer:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=max(1, settings.tts_prewarm_queue_size),
        )
        self._queued: set[str] = set()
        self._worker: asyncio.Task | None = None
        self._generated = 0
        self._failed = 0

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def generated(self) -> int:
        return self._generated

    @property
    def failed(self) -> int:
        return self._failed

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    def enqueue(self, texts: Iterable[str]) -> int:
        accepted = 0
        for raw in texts:
            text = clean_tts_text(raw)
            if not text:
                continue
            identity = text.casefold()
            if identity in self._queued:
                continue
            if self._queue.full():
                logger.warning('Priya prewarm queue full; dropping remaining fixed lines')
                break
            self._queued.add(identity)
            self._queue.put_nowait(text)
            accepted += 1

        if accepted:
            self._ensure_worker()
        return accepted

    async def _run(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                result = await parler_service.synthesize(text)
                self._generated += 1
                logger.info(
                    'Priya prewarm state=%s pending=%d hash=%s',
                    'cached' if result.cached else 'generated',
                    self._queue.qsize(),
                    result.audio_hash[:12],
                )
            except Exception:
                self._failed += 1
                logger.exception('Priya fixed-line prewarm failed')
            finally:
                self._queued.discard(text.casefold())
                self._queue.task_done()


curriculum_voice_prewarmer = CurriculumVoicePrewarmer()
