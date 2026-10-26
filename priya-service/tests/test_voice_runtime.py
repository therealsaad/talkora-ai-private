import asyncio
import importlib
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, PropertyMock, patch

from app.config import settings
from app.tts.parler_service import ParlerService, parler_service
from app.tts.voice_profiles import PRIYA_VOICE_ID


class VoiceRuntimeTests(unittest.TestCase):
    def test_fastapi_app_starts_with_the_cached_priya_service(self):
        module = importlib.import_module('app.main')

        self.assertEqual(module.tts_service.name, 'python-priya-cache')

    def test_health_reports_the_cached_priya_provider(self):
        module = importlib.import_module('app.main')

        with patch.object(
            module.qwen_client,
            'status',
            new=AsyncMock(return_value={'reachable': False, 'modelAvailable': False}),
        ), patch.object(
            ParlerService,
            'available',
            new_callable=PropertyMock,
            return_value=True,
        ), patch.object(
            ParlerService,
            'model_available',
            new_callable=PropertyMock,
            return_value=True,
        ), patch.object(
            type(module.whisper_service),
            'available',
            new_callable=PropertyMock,
            return_value=False,
        ), patch.object(
            type(module.whisper_service),
            'model_available',
            new_callable=PropertyMock,
            return_value=False,
        ), patch.object(module.torch.cuda, 'is_available', return_value=False):
            result = asyncio.run(module.health())

        self.assertEqual(result['ttsProvider'], 'python-priya-cache')
        self.assertIn('parlerImport', result)

    def test_known_lesson_line_is_served_from_the_existing_cache_identity(self):
        text = (
            'Welcome to Favourite Fair! Let us discover favourite things and '
            'learn how good conversations keep going.'
        )
        expected_hash = '01dc864b21dfb446a9774255ebfe597bbfef52ab7a2cd6db62da8133b6fc798a'

        with tempfile.TemporaryDirectory() as directory:
            original_storage_root = settings.storage_root
            settings.storage_root = Path(directory)
            try:
                audio = (
                    settings.storage_root
                    / 'tts'
                    / 'en-IN'
                    / PRIYA_VOICE_ID
                    / f'{expected_hash}.wav'
                )
                audio.parent.mkdir(parents=True)
                with wave.open(str(audio), 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(16_000)
                    output.writeframes(b'\x00\x00' * 1_600)

                with patch.object(
                    ParlerService,
                    'available',
                    new_callable=PropertyMock,
                    return_value=False,
                ):
                    result = asyncio.run(
                        parler_service.synthesize(
                            text,
                            voice=PRIYA_VOICE_ID,
                            language='en-IN',
                        )
                    )

                self.assertTrue(result.cached)
                self.assertEqual(result.audio_hash, expected_hash)
                self.assertEqual(Path(result.path), audio)
            finally:
                settings.storage_root = original_storage_root

    def test_current_priya_voice_reuses_a_valid_cache_file_from_the_legacy_folder(self):
        text = 'What do you like to do after school?'
        legacy_hash = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'

        with tempfile.TemporaryDirectory() as directory:
            original_storage_root = settings.storage_root
            settings.storage_root = Path(directory)
            try:
                audio = (
                    settings.storage_root
                    / 'tts'
                    / 'en-IN'
                    / 'priya'
                    / f'{legacy_hash}.wav'
                )
                audio.parent.mkdir(parents=True)
                with wave.open(str(audio), 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(16_000)
                    output.writeframes(b'\x00\x00' * 1_600)
                audio.with_suffix('.json').write_text(
                    json.dumps({
                        'audioHash': legacy_hash,
                        'text': text,
                        'voiceId': PRIYA_VOICE_ID,
                        'language': 'en-IN',
                        'model': 'ai4bharat/indic-parler-tts',
                    }),
                    encoding='utf-8',
                )

                with patch.object(
                    ParlerService,
                    'available',
                    new_callable=PropertyMock,
                    return_value=False,
                ):
                    result = asyncio.run(
                        parler_service.synthesize(
                            text,
                            voice=PRIYA_VOICE_ID,
                            language='en-IN',
                        )
                    )

                self.assertTrue(result.cached)
                self.assertEqual(result.audio_hash, legacy_hash)
                self.assertEqual(Path(result.path), audio)
            finally:
                settings.storage_root = original_storage_root


if __name__ == '__main__':
    unittest.main()
