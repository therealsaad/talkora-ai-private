# Talkora Phase 4 — KG1 compatibility pilot

This patch is built against the previously delivered Phase 1 and Phase 3 archives, **not** an independently inspected copy of your current local AI workspace. Back up or compare your local files before applying. Do not overwrite a modified local `server/main.py` blindly.

## Install (AI workspace only)
Copy `talkora-ai-starter/server/compat.py`, `talkora-ai-starter/phase3/kg1.json` and `talkora-ai-starter/tests/test_compat.py` to matching paths inside your existing `ai-models/talkora-ai-starter`. Add these two lines to the end of your existing `server/main.py` (only once):

```python
from .compat import router as compat_router
app.include_router(compat_router)
```

Keep `ai-models/Talkora_Phase3_Implementation` and your Node app intact. Run from `talkora-ai-starter`:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest tests/test_compat.py -q
python -m uvicorn server.main:app --host 127.0.0.1 --port 8002 --reload
```

Test in another terminal:

```powershell
$body = @{grade=0;levelId='g00-l01';studentMessage='apple';preferredExplanationLanguage='Hindi';currentQuestion='Say apple'} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8002/v1/brain/respond' -Method Post -ContentType 'application/json' -Body $body
```

## Node integration: NOT ENABLED YET
Your current `PythonAIProvider.ts` sends **no `levelId`**, and its `AI_SERVICE_URL` defaults to port 8001. Do **not** change `AI_PROVIDER` or `AI_SERVICE_URL` yet. First map the actual MongoDB lesson/activity to the canonical `g00-l01` in `StudentContextService` and add an explicit level ID to the provider request. The API deliberately returns 422 for missing or non-KG1 levels to prevent teaching the wrong curriculum. Existing Qwen provider remains separate.

## Limits
KG1 data has `teacher_review_required: true`; this endpoint is for local testing only. Do not expose it publicly or use it for production student traffic. Model output is not authoritative for assessment, mastery, or verified memory. Automated tests check routing guards and endpoint registration, not educational correctness or live Ollama quality.
