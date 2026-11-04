"""Authenticated opt-in local Qwen bridge for KG1–5 and Class 1 Level 1.
No other grade or lesson is enabled. No student data is persisted here.
"""
import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from .bridge_security import require_bridge_key

router = APIRouter()
PILOT = json.loads((Path(__file__).resolve().parents[1] / 'phase3/kg1.json').read_text(encoding='utf-8'))
EMOTIONS = {'welcome', 'encouraging', 'delighted', 'thinking', 'celebrating', 'gentle_correction', 'modeling', 'retry'}

# Exact KG2–5 approved *pilot* letter-to-picture context, not student publication.
# KG2 currently has letters only; KG5 words follow the Node student catalog,
# not the older, mismatched staff preview (wolf/yak rather than whale/yo-yo).
KG_LETTER_WORDS = {
    'g00-l02': dict.fromkeys('EFGHIJ', ''),
    'g00-l03': dict(zip('KLMNOP', ('kite', 'lion', 'monkey', 'nest', 'orange', 'parrot'))),
    'g00-l04': dict(zip('QRSTUV', ('queen', 'rabbit', 'sun', 'tiger', 'umbrella', 'van'))),
    'g00-l05': dict(zip('WXYZ', ('wolf', 'xylophone', 'yak', 'zebra'))),
}

def continuation_context(req: 'BrainRequest') -> dict[str, Any]:
    """Allow only one current letter and its known story word from Node."""
    import re
    if req.grade != 0 or req.levelId not in KG_LETTER_WORDS:
        raise HTTPException(422, 'Unsupported KG lesson')
    if os.getenv('TALKORA_KG2_5_QWEN_PILOT', '').strip().lower() != 'true':
        raise HTTPException(403, 'KG continuation AI pilot disabled')
    match = re.fullmatch(r'\s*Say the letter ([A-Z])\s*', req.currentQuestion, re.IGNORECASE)
    letter = match.group(1).upper() if match else ''
    word = KG_LETTER_WORDS[req.levelId].get(letter)
    if word is None:
        raise HTTPException(422, 'Requested KG letter is not in the current approved pilot')
    expected = {letter.lower()}
    if word:
        expected.add(word)
    supplied = {entry.lower().strip() for entry in req.allowedVocabulary}
    if supplied != expected:
        raise HTTPException(422, 'Unapproved KG word or letter context')
    if req.studentName != 'Learner' or req.conversationHistory or req.recentMistakes:
        raise HTTPException(422, 'Unexpected personal or historic KG context')
    return {'levelId': req.levelId, 'levelObjective': 'say the English letter',
            'currentLetter': letter, 'pictureWord': word,
            'allowedVocabulary': sorted(expected)}


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

@router.post('/v1/brain/respond', dependencies=[Depends(require_bridge_key)])
async def brain_respond(req: BrainRequest) -> dict[str, Any]:
    # Class 1 is opt-in and anchored to the authorized canonical level ID.
    # Do not change the existing KG handler or teach any other class here.
    if req.grade == 1 and req.levelId == 'g01-l01':
        if os.getenv('TALKORA_CLASS1_QWEN_PILOT', '').lower() != 'true':
            raise HTTPException(403, 'Class 1 AI pilot is disabled')
        from .class1 import respond_class1
        from .class1_response_guard import guard_class1_response
        return guard_class1_response(await respond_class1(req), req)

    # Route only the explicit KG2–5 letter pilots, never draft KG6–10.
    # This bridge can compose language, but Node remains sole grading authority.
    if req.grade == 0 and req.levelId in KG_LETTER_WORDS:
        lesson = continuation_context(req)
    elif req.grade == 0 and req.levelId == 'g00-l01':
        lesson = PILOT
    else:
        raise HTTPException(422, 'Only explicit KG Level 1–5 pilots are authored; no grade fallback')
    language = {'hindi':'hi','marathi':'mr','english':'en','hi':'hi','mr':'mr','en':'en'}.get(req.preferredExplanationLanguage.lower())
    if language is None:
        raise HTTPException(422, 'Unsupported explanation language')
    system = (
        'You are Miss Julie, a kind spoken-English teacher for KG children. '
        'The child may respond with a single word. Do not claim a correct answer unless it is supported by the student utterance. '
        'Stay strictly within the supplied lesson, activity and teacher question. '
        'For continuation KG2–5, ONLY answer the child briefly and then ask the current English LETTER. '
        'Do not imply that recognizing a picture word completes the letter task. '
        'Never ask for private details or provide unsafe unrelated instructions. '
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
        + json.dumps({'lesson':lesson,'language':language,'currentQuestion':req.currentQuestion,
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
