"""Opt-in pilot bridge for existing Node PythonAIProvider contract.
No other grade or lesson is enabled. No student data is persisted here.
"""
import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

router = APIRouter()
PILOT = json.loads((Path(__file__).resolve().parents[1] / 'phase3/kg1.json').read_text(encoding='utf-8'))
EMOTIONS = {'welcome', 'encouraging', 'delighted', 'thinking', 'celebrating', 'gentle_correction', 'modeling', 'retry'}

class BrainRequest(BaseModel):
    model_config = ConfigDict(extra='allow')
    studentName: str = Field(default='Learner', max_length=80)
    grade: int = Field(ge=0, le=10)
    levelId: str = Field(min_length=1, max_length=20)
    studentMessage: str = Field(min_length=1, max_length=1000)
    preferredExplanationLanguage: str = 'English'
    activityTitle: str = ''
    currentQuestion: str = ''
    learningObjectives: list[str] = Field(default_factory=list)
    allowedVocabulary: list[str] = Field(default_factory=list)
    recentMistakes: list[str] = Field(default_factory=list)
    conversationHistory: list[str] = Field(default_factory=list)
    waitingForRetry: bool = False
    hintLevel: int = 0

@router.post('/v1/brain/respond')
async def brain_respond(req: BrainRequest) -> dict[str, Any]:
    # Class 1 is opt-in and anchored to the authorized canonical level ID.
    # Do not change the existing KG handler or teach any other class here.
    if req.grade == 1 and req.levelId == 'g01-l01':
        if os.getenv('TALKORA_CLASS1_QWEN_PILOT', '').lower() != 'true':
            raise HTTPException(403, 'Class 1 AI pilot is disabled')
        from .class1 import respond_class1
        from .class1_response_guard import guard_class1_response
        return guard_class1_response(await respond_class1(req), req)

    # Deliberately fail closed: never silently route Class 4 or another KG level into KG1.
    if req.grade != 0 or req.levelId != 'g00-l01':
        raise HTTPException(422, 'Only explicit KG Level 1 pilot is authored; no grade fallback')
    language = {'hindi':'hi','marathi':'mr','english':'en','hi':'hi','mr':'mr','en':'en'}.get(req.preferredExplanationLanguage.lower())
    if language is None:
        raise HTTPException(422, 'Unsupported explanation language')
    system = (
        'You are Miss Julie, a kind spoken-English teacher for KG children. '
        'The child may respond with a single word. Do not claim a correct answer unless it is supported by the student utterance. '
        'Stay strictly within the supplied lesson, activity and teacher question. '
        'Respond in simple spoken English; a brief support-language hint may be included if needed. '
        'Never emit metadata like hi: or mr: in spoken text. Do not ask for identifying information. '
        'Return one JSON object containing: message, reaction, responseQuality, followUpQuestion, '
        'correction (needed, original, corrected, explanation), recommendedAction, teachingAction, '
        'modelSentence, activityComplete, shouldRetry, hintLevel, detectedSkills, remainingSkills. '
        'reaction must be one of welcome, encouraging, delighted, thinking, celebrating, gentle_correction, modeling, retry. '
        'responseQuality must be STRONG, ADEQUATE, PARTIAL or UNCLEAR. '
        'teachingAction must be CONTINUE_CONVERSATION, GENTLE_CORRECTION, MODEL_SENTENCE, WAIT_FOR_REPEAT, '
        'CELEBRATE_IMPROVEMENT, ASK_FOLLOW_UP, GIVE_HINT or CLARIFY. '
        'Never mark activityComplete true; the Node backend owns mastery and completion. '
        'Use no memoryUpdates; the Node backend owns memory verification.\n'
        + json.dumps({'lesson':PILOT,'language':language,'currentQuestion':req.currentQuestion,
                      'activityTitle':req.activityTitle,'objectives':req.learningObjectives,
                      'allowedVocabulary':req.allowedVocabulary,'recentMistakes':req.recentMistakes[-5:],
                      'history':req.conversationHistory[-6:],'waitingForRetry':req.waitingForRetry,
                      'hintLevel':req.hintLevel},ensure_ascii=False)
    )
    url = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    if url not in ('http://127.0.0.1:11434','http://localhost:11434'):
        raise HTTPException(503, 'Pilot accepts local Ollama only')
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            result = await client.post(url+'/api/chat',json={'model':os.getenv('OLLAMA_MODEL','qwen3:4b-instruct'),
                'stream':False,'format':'json','options':{'temperature':0.2,'num_predict':350},
                'messages':[{'role':'system','content':system},{'role':'user','content':req.studentMessage}]})
            result.raise_for_status()
            data = json.loads(result.json()['message']['content'])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, 'Local Qwen unavailable or invalid JSON') from exc
    if not isinstance(data,dict) or not isinstance(data.get('message'),str) or not data['message'].strip():
        raise HTTPException(502, 'Missing teacher message')
    quality = data.get('responseQuality','ADEQUATE')
    if quality not in ('STRONG','ADEQUATE','PARTIAL','UNCLEAR'): quality='ADEQUATE'
    reaction = data.get('reaction','encouraging')
    if reaction not in EMOTIONS: reaction='encouraging'
    actions = {'CONTINUE_CONVERSATION','GENTLE_CORRECTION','MODEL_SENTENCE','WAIT_FOR_REPEAT','CELEBRATE_IMPROVEMENT','ASK_FOLLOW_UP','GIVE_HINT','CLARIFY'}
    action = data.get('teachingAction','CONTINUE_CONVERSATION')
    if action not in actions: action='CONTINUE_CONVERSATION'
    correction = data.get('correction')
    if not isinstance(correction,dict): correction={}
    correction = { 'needed':bool(correction.get('needed',False)),
      'original':str(correction.get('original',''))[:300],
      'corrected':str(correction.get('corrected',''))[:300],
      'explanation':str(correction.get('explanation',''))[:300] }
    return {'message':data['message'].strip()[:700], 'reaction':reaction, 'responseQuality':quality,
      'followUpQuestion':str(data['followUpQuestion'])[:250] if data.get('followUpQuestion') else None,
      'correction':correction, 'memoryUpdates':[], 'recommendedAction':action,'teachingAction':action,
      'modelSentence':str(data['modelSentence'])[:300] if data.get('modelSentence') else None,
      'activityComplete':False,'shouldRetry':bool(data.get('shouldRetry',False)),
      'hintLevel':max(0,min(3,int(data.get('hintLevel',0)) if str(data.get('hintLevel',0)).isdigit() else 0)),
      'detectedSkills':[str(x) for x in data.get('detectedSkills',[])[:12]] if isinstance(data.get('detectedSkills'),list) else [],
      'remainingSkills':[str(x) for x in data.get('remainingSkills',[])[:12]] if isinstance(data.get('remainingSkills'),list) else []}
