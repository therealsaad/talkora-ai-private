"""Offline FastAPI 8001 diagnostics. No torch/model weights/paid APIs required."""
import asyncio
import importlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


class Priya8001ContractTests(unittest.TestCase):

    def test_invalid_voice_validation_error_returns_safe_422_json(self):
        app = importlib.import_module('app.main')
        # Mirrors Pydantic's real invalid-voice error, including a ValueError
        # inside ctx. Previously JSONResponse tried to serialize that object,
        # raising a TypeError and reporting HTTP 500 instead of HTTP 422.
        validation = RequestValidationError([{
            'type': 'value_error',
            'loc': ('body', 'voice'),
            'msg': 'Unsupported Talkora voice',
            'input': 'secret student transcript or invalid voice',
            'ctx': {'error': ValueError('Unsupported Talkora voice')},
        }])
        response = asyncio.run(app.validation_error(None, validation))
        result = json.loads(response.body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(result['error']['code'], 'VALIDATION_ERROR')
        self.assertEqual(result['error']['details'][0]['loc'], ['body', 'voice'])
        self.assertNotIn('input', result['error']['details'][0])
        self.assertNotIn('ctx', result['error']['details'][0])
        self.assertNotIn('secret student transcript', response.body.decode())

    def test_unknown_voice_is_rejected_before_model_inference(self):
        app = importlib.import_module('app.main')
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            app.TTSRequest(text='Hello Grade One!', voice='miss-julie-priya-v6')

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
