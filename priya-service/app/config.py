"""Talkora AI Service configuration.

All configuration is environment-driven (see .env.example). Only settings for
the ACTIVE provider are required at startup — see config_validation.py for
the fail-fast checks that run once, during application startup, rather than
at import time (importing this module must never require secrets to exist,
since tests import it freely).
"""
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    # --------------------------------------------------------------- app --
    app_env: Literal['development', 'test', 'production'] = 'development'
    host: str = '0.0.0.0'
    port: int = 8001
    log_level: str = 'INFO'
    log_json: bool = False

    # Service-to-service auth. Empty string disables the check (development
    # only — see config_validation.py, which requires this in production).
    ai_service_api_key: str = ''

    # Comma-separated origins, e.g. "https://app.talkora.com,https://admin.talkora.com".
    # Empty means "no browser origins allowed" (the browser should talk to the
    # Node backend, not this service, in production).
    cors_allowed_origins: str = ''

    # Allow AI_PROVIDER=mock / STT_PROVIDER=mock / TTS_PROVIDER=mock. Refused
    # outside development unless explicitly set true (see config_validation.py).
    allow_mock_providers: bool = False

    max_audio_upload_mb: float = 8.0
    request_id_header: str = 'X-Request-Id'
    service_auth_header: str = 'X-Service-API-Key'

    # ------------------------------------------------------------- brain --
    ai_provider: Literal['openai', 'ollama', 'mock'] = 'openai'

    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    openai_timeout_seconds: float = 20.0
    openai_max_output_tokens: int = 350
    openai_temperature: float = 0.3
    openai_max_retries: int = 2
    openai_base_url: str = ''  # override for Azure/OpenAI-compatible gateways

    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen3:4b-instruct'
    ollama_timeout_seconds: float = 80.0
    ollama_keep_alive: str = '10m'
    # RTX 4050 Laptop 6 GB dev policy: reserve CUDA for Priya, keep Qwen on CPU.
    ollama_num_gpu: int | None = 0

    brain_max_history_turns: int = 8
    brain_max_memory_facts: int = 8
    brain_max_mistakes: int = 5

    # ---------------------------------------------------------------- stt --
    stt_provider: Literal['groq', 'local', 'mock'] = 'groq'

    groq_api_key: str = ''
    groq_stt_model: str = 'whisper-large-v3-turbo'
    groq_timeout_seconds: float = 20.0
    groq_max_retries: int = 2
    groq_base_url: str = 'https://api.groq.com/openai/v1'

    # Local faster-whisper fallback/dev provider.
    stt_local_model: str = 'small.en'
    stt_local_device: str = 'cpu'
    stt_local_compute_type: str = 'int8'
    stt_provider: str = "groq"
    stt_model: str = "small"
    groq_stt_model: str = "whisper-large-v3-turbo"

    # ---------------------------------------------------------------- tts --
    tts_provider: str = 'priya'
    tts_model: str = 'ai4bharat/indic-parler-tts'
    tts_voice: str = 'Priya'
    tts_language: str = 'en-IN'
    tts_style_version: str = 'talkora-priya-v6-indian-kids-teacher'
    tts_concurrency: int = 1
    tts_unload_after_generation: bool = False
    tts_attention_implementation: str = 'eager'
    tts_device: str = 'cuda'
    tts_warm_on_startup: bool = False
    tts_prewarm_queue_size: int = 2500
    tts_max_text_length: int = 600
    # Explicit CUDA fallback policy (see config_validation.py / readiness).
    tts_allow_cpu_fallback: bool = False

    # ---------------------------------------------------- local model cache --
    # The workstation already has the models. Never silently download at runtime.
    hf_cache_dir: Path = Path.home() / '.cache' / 'huggingface' / 'hub'
    models_local_only: bool = True
    hf_token: str = ''

    # Reserved for a future acoustic/IndicF5 provider; unused by the active
    # Parler-based Priya provider today.
    indicf5_model: str = 'ai4bharat/IndicF5'
    indicf5_ref_audio_path: str = ''
    indicf5_ref_text: str = ''
    indicf5_device: str = 'cuda'
    indicf5_sample_rate: int = 24000

    storage_root: Path = Path(__file__).resolve().parents[1] / 'storage'

    @field_validator('cors_allowed_origins', mode='before')
    @classmethod
    def _normalize_cors(cls, value: object) -> str:
        return '' if value is None else str(value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(',') if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == 'production'


settings = Settings()
