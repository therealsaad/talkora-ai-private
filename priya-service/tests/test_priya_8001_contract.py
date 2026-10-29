"""Offline FastAPI 8001 diagnostics. No torch/model weights/paid APIs required."""
import asyncio
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from fastapi import HTTPException


class Priya8001ContractTests(unittest.TestCase):
    def test_health_exposes_configured_device_before_cold_start(self):
        app = importlib.import_module('app.main')
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.object(app, 'torch', fake_torch), \
             patch.object(app.qwen_client, 'status', new=AsyncMock(
                 return_value={'reachable': False, 'modelAvailable': False})), \
             patch.object(type(app.tts_service), 'available',
                          new_callable=PropertyMock, return_value=True), \
             patch.object(type(app.tts_service), 'model_available',
                          new_callable=PropertyMock, return_value=True):
            result = asyncio.run(app.health())
        self.assertEqual(result['ttsConfiguredDevice'], app.settings.tts_device)
        self.assertTrue(result['ttsVoiceId'])
        self.assertFalse(result['cuda'])

    def test_unhandled_generation_error_is_sanitized_without_model_loading(self):
        app = importlib.import_module('app.main')
        with patch.object(app, '_synthesize_priya',
                          new=AsyncMock(side_effect=OSError('blocked private DLL path'))):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(app.tts(app.TTSRequest(text='Hello Grade One!', voice='Priya')))
        exc = raised.exception
        self.assertEqual(exc.status_code, 503)
        self.assertEqual(exc.detail['code'], 'TTS_GENERATION_FAILED')
        self.assertNotIn('blocked private DLL path', exc.detail['message'])
