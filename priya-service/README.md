# Talkora internal AI service

This FastAPI process is private infrastructure behind the authenticated Express API. The browser must never call it directly.

It provides:

- bounded Miss Julie responses from local Ollama `qwen3:4b-instruct`;
- Priya Indic Parler-TTS speech with a single versioned voice profile and deterministic WAV cache;
- faster-whisper transcription;
- transcript-based “Words Heard Clearly” feedback (not an acoustic pronunciation score).

## Local start

1. Copy `.env.example` to `.env` and adjust local model paths if needed.
2. Ensure Ollama is running and `ollama list` contains `qwen3:4b-instruct`.
3. Activate `.venv`, install `requirements.txt`, and install Indic Parler-TTS from its upstream repository if it is not already available.
4. Run `uvicorn app.main:app --host 127.0.0.1 --port 8001`.
5. Start the Express backend with `AI_PROVIDER=python`, `VOICE_PROVIDER=python`, `SPEECH_PROVIDER=python`, and `PRONUNCIATION_PROVIDER=python`.

Run lightweight tests with `python -m unittest discover -s tests`.

Static curriculum narration can be generated ahead of time with `python generate_curriculum_audio.py --unit 1`. Runtime speech reuses the same cache and voice profile.
