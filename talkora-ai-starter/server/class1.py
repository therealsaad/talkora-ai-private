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
from .class1_language import resolve_support_language

LESSON = json.loads((Path(__file__).resolve().parents[1] / 'phase3/class1.json').read_text(encoding='utf-8'))
WORDS = set(LESSON['approved_foundation_words'])
if WORDS != FOUNDATION_WORDS:
    raise ValueError('Class 1 adaptive vocabulary disagrees with the existing pilot')
SENTENCES = {**LESSON['model_sentences'], 'school': 'I am at school.',
             'walk': 'I walk to school.'}


def authored_coaching(language: str, *, target: str | None,
                      observed: bool | None, school_story: bool,
                      supported_sentence: bool, mode: str) -> tuple[str, str]:
    """Original, educator-reviewable scaffolds, never model-generated claims.

    Keep the word being taught in English even when the explanation is in a
    home language. Output is intentionally bounded, fast and costs no GPU.
    """
    if target:
        if observed is True:
            if mode == 'EXTEND' and school_story:
                pairs = {
                    'en': (f'Nice effort saying {target}! Let us use it at school.',
                           'Can you say: I am at school?'),
                    'hi': (f'बहुत अच्छी कोशिश! अब {target} को स्कूल की बात में बोलेंगे।',
                           'अंग्रेज़ी में बोलो: I am at school.'),
                    'mr': (f'छान प्रयत्न! आता {target} शाळेबद्दलच्या वाक्यात वापरू.',
                           'इंग्रजीत म्हण: I am at school.'),
                }
                return pairs[language]
            pairs = {
                'en': (f'I heard {target}. Nice effort!',
                       f'Can you say {target} once more?'),
                'hi': (f'मैंने {target} सुना। अच्छी कोशिश!',
                       f'क्या तुम {target} एक बार और बोलोगे?'),
                'mr': (f'मला {target} ऐकू आलं. छान प्रयत्न!',
                       f'{target} पुन्हा एकदा म्हणशील का?'),
            }
            return pairs[language]
        if observed is False:
            pairs = {
                'en': (f'No worries. Listen carefully: {target}. Let us try together.',
                       f'Say {target} with me.'),
                'hi': (f'कोई बात नहीं। ध्यान से सुनो: {target}। साथ में बोलते हैं।',
                       f'मेरे साथ {target} बोलो।'),
                'mr': (f'काही हरकत नाही. नीट ऐक: {target}. आपण एकत्र म्हणू.',
                       f'माझ्यासोबत {target} म्हण.'),
            }
            return pairs[language]
    if supported_sentence:
        pairs = {
            'en': ('I heard you talking about school. Nice effort!',
                   'Can you tell me one more thing about school?'),
            'hi': ('तुमने स्कूल के बारे में बताया। बहुत अच्छी कोशिश!',
                   'स्कूल के बारे में एक और बात अंग्रेज़ी में बताओ।'),
            'mr': ('तू शाळेबद्दल सांगितलंस. छान प्रयत्न!',
                   'शाळेबद्दल अजून एक गोष्ट इंग्रजीत सांग.'),
        }
        return pairs[language]
    if school_story:
        pairs = {
            'en': ('Let us talk about school together.', 'Can you say school?'),
            'hi': ('चलो स्कूल की बात करते हैं।', 'अंग्रेज़ी में school बोलो।'),
            'mr': ('चला, शाळेबद्दल बोलूया.', 'इंग्रजीत school म्हण.'),
        }
        return pairs[language]
    pairs = {
        'en': ('Let us try a little English word together.', 'Can you say at?'),
        'hi': ('चलो, एक छोटा अंग्रेज़ी शब्द सीखते हैं।', 'मेरे साथ at बोलो।'),
        'mr': ('चला, एक छोटा इंग्रजी शब्द शिकूया.', 'माझ्यासोबत at म्हण.'),
    }
    return pairs[language]


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
    lang = resolve_support_language(req.preferredExplanationLanguage, req.studentMessage)
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
    supported_sentence = target is None and has_supported_school_sentence(
        req.currentQuestion, req.activityTitle, req.studentMessage
    )
    school_story = bool(set(curriculum_context(req.currentQuestion, req.activityTitle)
                            ['approved_vocabulary']) & CONTEXT_WORDS)
    baseline, follow_up = authored_coaching(
        lang, target=target, observed=observed, school_story=school_story,
        supported_sentence=supported_sentence, mode=plan.mode,
    )
    if supported_sentence:
        quality, action, retry = 'ADEQUATE', 'ASK_FOLLOW_UP', False
    elif target is None or observed is None:
        quality, action, retry = 'UNCLEAR', 'CLARIFY', False
    elif observed:
        quality, action, retry = 'ADEQUATE', 'ASK_FOLLOW_UP', False
    else:
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
