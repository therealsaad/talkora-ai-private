"""Class 1 Level 1 Qwen bridge for the existing Talkora /v1/brain/respond route.

Draft *foundations* content only; not a Balbharati textbook transcription.
Lexical transcript evidence is NOT phonetic/pronunciation or mastery evidence.
"""
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from .class1_adaptive import (CONTEXT_WORDS, FOUNDATION_WORDS, SYSTEM_INSTRUCTIONS,
                              curriculum_context, has_supported_school_sentence,
                              is_simple_repeat, select_teaching_plan)
from .class1_hint_gate import validate_model_hint

LESSON = json.loads((Path(__file__).resolve().parents[1] / 'phase3/class1.json').read_text(encoding='utf-8'))
WORDS = set(LESSON['approved_foundation_words'])
if WORDS != FOUNDATION_WORDS:
    raise ValueError('Class 1 adaptive vocabulary disagrees with the existing pilot')
SENTENCES = {**LESSON['model_sentences'], 'school': 'I am at school.',
             'walk': 'I walk to school.'}


def active_target(question: str, activity: str = '') -> str | None:
    """Find the active target ONLY from server-resolved teacher prompts, not pupil input."""
    source = (question or '') + ' ' + (activity or '')
    clean = re.sub(r"[^a-z0-9\s'-]", ' ', source.lower())
    if re.search(r'\bi\s+am\s+sam\b', clean):
        return 'i am sam'
    if re.search(r'\blook\s+__\s+me\b', source.lower()):
        return 'at'  # Fill-the-blank requires the word, not the whole sentence.
    if re.search(r'\blook\s+at\s+me\b', source.lower()):
        return 'look at me'
    # Limit extraction to prompts that identify the expected word explicitly.
    # Do NOT guess from arbitrary activity names or what the child happened to say.
    pattern = (r'\b(?:which\s+word\s+is|word|say|repeat|spell|build|find|read|'
               r'practice|practise|choose|write|listen\s+to)\s+'
               r'(?:the\s+word\s+|is\s+)?[\"\']?'
               r'(am|an|at|in|is|it|on|up|school|walk)\b')
    matches = re.findall(pattern, clean)
    return matches[-1] if matches else None


def observed_target(message: str, target: str | None) -> bool | None:
    if target is None:
        return None
    normalized = ' '.join(re.findall(r"[a-z]+", message.lower()))
    if not normalized:
        return None
    if target in ('look at me', 'i am sam'):
        return target in normalized
    return bool(re.search(r'\b' + re.escape(target) + r'\b', normalized))


def safe_line(line: Any) -> str:
    """Use Qwen only for a short, non-grading coaching hint; block unsafe/unanchored claims."""
    if not isinstance(line, str):
        return ''
    line = ' '.join(line.strip().split())
    if not line or len(line) > 130 or len(line.split()) > 12 or line.count('.') > 2 or '\n' in line:
        return ''
    forbidden = (
        r'https?://|www\.|(?:https?|mailto):|\b(?:phone|address|password|secret)\b|'
        r'\b(?:photo|picture|image|screen)\b|\b(?:perfect|flawless)\b|'
        r'\b(?:pronunciation|accent)\b|\b(?:correct|incorrect|right|wrong|score|passed)\b'
    )
    if re.search(forbidden, line, flags=re.IGNORECASE):
        return ''
    return line


async def query_qwen(target: str | None, transcript: str, observed: bool | None,
                     language: str, question: str, *, plan: Any = None,
                     activity: str = '') -> str:
    """Model supplies an optional child-friendly coaching hint, never the grade."""
    # The V2 adapter failed held-out QA. Existing scripted lesson feedback stays
    # usable while model hints require a separate educator-approved feature gate.
    # Do not enable for bilingual model output, unknown targets, or sentence IDs.
    if os.getenv('TALKORA_CLASS1_HINTS_APPROVED', '').lower() != 'true':
        return ''
    if target not in (FOUNDATION_WORDS | CONTEXT_WORDS) or language != 'en':
        return ''
    url = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    if url not in ('http://127.0.0.1:11434', 'http://localhost:11434'):
        raise HTTPException(503, 'Class 1 pilot permits local Ollama only')
    model = os.getenv('OLLAMA_MODEL', 'qwen3:4b-instruct')
    context = curriculum_context(question, activity)
    payload = {'target':target, 'transcript':transcript[:240],
               'word_visible_in_transcript':observed,
               'support_language':language, 'teacher_question':question[:200],
               'approved_vocabulary':context['approved_vocabulary'],
               'lesson_unit':context['unit'], 'learning_goal':context['learning_goal'],
               'scaffold_mode':plan.mode if plan else 'GUIDE',
               'scaffold_instruction':plan.instruction if plan else 'Offer a small hint.'}
    try:
        # Keep voice-first lessons responsive if local Ollama is busy or cold.
        async with httpx.AsyncClient(timeout=3.0) as client:
            result = await client.post(url + '/api/chat', json={
                'model':model, 'stream':False, 'format':'json',
                'options':{'temperature':0.0,'num_predict':64},
                'messages':[{'role':'system','content':SYSTEM_INSTRUCTIONS},
                            {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
            })
            result.raise_for_status()
            raw = result.json()['message']['content']
        candidate = validate_model_hint(
            raw, target=target, language=language,
            mode=plan.mode if plan else 'GUIDE',
        )
        return safe_line(candidate)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        # The fixed lesson response remains usable if Ollama is cold or down;
        # model output is supplementary coaching, never the source of grading.
        return ''


async def respond_class1(req: Any) -> dict[str, Any]:
    if req.grade != 1 or req.levelId != 'g01-l01':
        raise HTTPException(422, 'Only Class 1 Level 1 is authored for this pilot')
    lang = {'english':'en','hindi':'hi','marathi':'mr','en':'en','hi':'hi','mr':'mr'}.get(
        req.preferredExplanationLanguage.lower())
    if lang is None:
        raise HTTPException(422, 'Unsupported explanation language')
    target = active_target(req.currentQuestion, req.activityTitle)
    observed = observed_target(req.studentMessage, target)
    plan = select_teaching_plan(req, observed, target)
    # The response guard supplies deterministic repeat feedback anyway. Avoid
    # an unnecessary GPU round trip for this latency-sensitive micro-activity.
    hint = '' if is_simple_repeat(req.currentQuestion, req.activityTitle, target) else (
        await query_qwen(target, req.studentMessage, observed, lang,
                         req.currentQuestion, plan=plan, activity=req.activityTitle)
    )
    if target is None and has_supported_school_sentence(
        req.currentQuestion, req.activityTitle, req.studentMessage
    ):
        baseline = 'I heard you talk about school. Nice effort!'
        follow_up = 'Can you tell me one more thing about your school day?'
        quality, action, retry = 'ADEQUATE', 'ASK_FOLLOW_UP', False
    elif target is None or observed is None:
        school_story = bool(set(curriculum_context(req.currentQuestion, req.activityTitle)
                                ['approved_vocabulary']) & CONTEXT_WORDS)
        baseline = ('Thank you for sharing. Let us talk about school together.' if school_story
                    else 'Let us try a short English word together.')
        follow_up = ('Can you tell me one thing about school?' if school_story
                     else 'Can you say at?')
        quality, action, retry = 'UNCLEAR', 'CLARIFY', False
    elif observed:
        baseline = f'I heard the word {target}. Nice effort!'
        follow_up = f'Can you use {target} in a little sentence?'
        quality, action, retry = 'ADEQUATE', 'ASK_FOLLOW_UP', False
    else:
        baseline = f'Thank you for trying. Let us practise {target} together.'
        follow_up = f'Can you try saying {target} once more?'
        quality, action, retry = 'PARTIAL', 'GIVE_HINT', True
    # Constrain the model to optional coaching only. It cannot award grades,
    # override the teacher question, or complete the lesson.
    spoken = baseline + ((' ' + hint) if hint else '')
    return {
        'message': spoken[:330], 'reaction':'encouraging' if observed else 'modeling',
        'responseQuality':quality, 'followUpQuestion':follow_up[:250],
        'correction':{'needed':False,'original':'','corrected':'','explanation':''},
        'memoryUpdates':[], 'recommendedAction':action,'teachingAction':action,
        'modelSentence':SENTENCES.get(target) if target else None,
        'activityComplete':False,'shouldRetry':retry,
        'hintLevel':min(3,max(0,int(req.hintLevel)) + (1 if retry else 0)),
        'detectedSkills':[], 'remainingSkills':[],
    }
