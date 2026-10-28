import json
import os
from pathlib import Path
from server.compat import router as compat_router
import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from server.bridge_security import require_bridge_key, require_experimental_chat_approval

ROOT = Path(__file__).resolve().parents[1]
# Only load the small, version-controlled pilot fixtures. Training datasets are
# deliberately gitignored and must never be a runtime startup dependency.
PILOT_LESSON_FILES = (ROOT / 'phase3/kg1.json', ROOT / 'phase3/class1.json')
LESSONS = {
    lesson['level_id']: lesson
    for path in PILOT_LESSON_FILES
    for lesson in [json.loads(path.read_text(encoding='utf-8'))]
}
SYSTEM = (ROOT / 'prompts/miss_julie.txt').read_text(encoding='utf-8')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
MODEL = os.getenv('OLLAMA_MODEL', 'qwen3:4b-instruct')
app = FastAPI(title='Talkora Miss Julie AI Prototype')
app.include_router(compat_router)

class ChatRequest(BaseModel):
    level_id: str
    message: str = Field(min_length=1, max_length=500)

class ChatResponse(BaseModel):
    reply: str
    hint: str
    next_question: str
    feedback: str
    level_id: str
    model: str

@app.get('/health')
def health():
    return {'status': 'ok', 'model': MODEL, 'levels': list(LESSONS)}

@app.post('/chat', response_model=ChatResponse,
          dependencies=[Depends(require_bridge_key), Depends(require_experimental_chat_approval)])
async def chat(req: ChatRequest):
    lesson = LESSONS.get(req.level_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail='Unknown lesson ID')
    messages = [
        {'role': 'system', 'content': SYSTEM + '\nLesson context:\n' + json.dumps(lesson, ensure_ascii=False)},
        {'role': 'user', 'content': req.message},
    ]
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            result = await client.post(f'{OLLAMA_URL}/api/chat', json={
                'model': MODEL, 'messages': messages, 'stream': False,
                'format': 'json', 'options': {'temperature': 0.3, 'num_predict': 220}
            })
            result.raise_for_status()
            raw = result.json()['message']['content']
            payload = json.loads(raw)
            return ChatResponse(level_id=req.level_id, model=MODEL,
                                **{k: str(payload.get(k, '')) for k in ('reply', 'hint', 'next_question', 'feedback')})
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail='Local model failed to return a valid response') from exc
