import logging
import json
import re
import time

import httpx
from .prompts import system_prompt, user_prompt
from .schemas import BrainRequest, BrainResponse, Correction, MemoryUpdate
from ..config import settings


class QwenUnavailable(RuntimeError):
    pass


logger = logging.getLogger('talkora.qwen')


def validate_qwen_payload(content: str) -> BrainResponse:
    """Accept useful Qwen JSON while coercing presentation-only schema drift."""
    payload = json.loads(extract_json_payload(content))
    if not isinstance(payload, dict):
        raise ValueError('Qwen response was not a JSON object.')

    allowed_reactions = {
        'greeting', 'welcome', 'curious', 'listening', 'thinking', 'delighted',
        'encouraging', 'gentle_correction', 'modeling', 'proud', 'surprised',
        'retry', 'gentle_retry', 'hinting', 'celebrating',
    }
    reaction = str(payload.get('reaction', 'encouraging')).lower()
    if reaction not in allowed_reactions:
        payload['reaction'] = 'encouraging'

    if not isinstance(payload.get('correction'), dict):
        payload['correction'] = {
            'needed': False, 'original': '', 'corrected': '', 'explanation': '',
        }

    allowed_actions = {
        'CONTINUE',
        'ACKNOWLEDGE',
        'CONTINUE_CONVERSATION',
        'RETRY',
        'GENTLE_CORRECTION',
        'OFFER_OPTIONS',
        'ASK_FOLLOW_UP',
        'MODEL_FULL_SENTENCE',
        'MODEL_SENTENCE',
        'WAIT_FOR_REPEAT',
        'PROMPT_STUDENT_QUESTION',
        'GIVE_HINT',
        'CELEBRATE_IMPROVEMENT',
        'CLARIFY',
        'COMPLETE_EPISODE',
        'COMPLETE',
    }
    action = str(payload.get('teachingAction') or payload.get('recommendedAction', 'CONTINUE')).upper()
    normalized_action = action if action in allowed_actions else 'CONTINUE'
    payload['teachingAction'] = normalized_action
    payload['recommendedAction'] = normalized_action
    payload['activityComplete'] = bool(payload.get('activityComplete', False))
    quality = str(payload.get('responseQuality', 'ADEQUATE')).upper()
    payload['responseQuality'] = quality if quality in {'STRONG', 'ADEQUATE', 'PARTIAL', 'UNCLEAR'} else 'ADEQUATE'
    payload['shouldRetry'] = bool(payload.get('shouldRetry', False))
    payload['hintLevel'] = max(0, min(3, int(payload.get('hintLevel', 0) or 0)))
    payload['modelSentence'] = payload.get('modelSentence') or None
    payload['detectedSkills'] = payload.get('detectedSkills', []) if isinstance(payload.get('detectedSkills', []), list) else []
    payload['remainingSkills'] = payload.get('remainingSkills', []) if isinstance(payload.get('remainingSkills', []), list) else []

    valid_memory = []
    for update in payload.get('memoryUpdates', []) if isinstance(payload.get('memoryUpdates'), list) else []:
        try:
            valid_memory.append(MemoryUpdate.model_validate(update).model_dump())
        except Exception:
            continue
    payload['memoryUpdates'] = valid_memory[:3]

    return BrainResponse.model_validate(payload)


def _curriculum_follow_up_question(request: BrainRequest, fallback: str | None = None) -> str:
    """Keep follow-up questions anchored to the live student lesson, never generic trivia."""
    current_question = (request.currentQuestion or '').lower()
    student_message = (request.studentMessage or '').lower()

    for skill in request.remainingConcepts:
        if skill in {'state_preference', 'warmup_spoken_participation'}:
            current_item = re.search(r"(?:like|don'?t like) ((?:eating|playing|doing) [a-z ]+?)(?:[.!]|\s+or\b|$)", current_question)
            return f'Do you like {current_item.group(1).strip()}?' if current_item else 'Tell me what you like in a whole sentence.'
        if skill == 'sport_company':
            return 'Who do you usually play your favourite sport with?'
        if skill == 'sport_reason':
            return 'Why do you like your favourite sport?'
        if skill == 'favourite_subject':
            return 'What is your favourite subject?'
        if skill == 'subject_reason':
            return 'Why do you like your favourite subject?'
        if skill in {'ask_julie_question', 'ask_favourite_question'}:
            return 'Now ask me a question about my favourite sport.'

    favourites = {
        'sport': 'Why do you like your favourite sport?',
        'food': 'Why do you like your favourite food?',
        'subject': 'Why do you like your favourite subject?',
        'animal': 'Why do you like your favourite animal?',
        'place': 'Why do you like your favourite place?',
        'festival': 'Why do you like your favourite festival?',
    }
    for key, question in favourites.items():
        if key in current_question or key in student_message:
            return question
    if any(word in student_message for word in ('cricket', 'football', 'basketball', 'hockey', 'badminton')):
        return 'Why do you like your favourite sport?'
    if fallback and 'why' in fallback.lower() and 'favourite' in fallback.lower():
        return fallback.strip()
    return 'Why do you like your favourite sport?'


def normalize_response(result: BrainResponse, request: BrainRequest) -> BrainResponse:
    """Apply deterministic validation/guardrails to real Qwen output."""
    message = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27BF]', '', result.message).strip()
    follow_up = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27BF]', '', result.followUpQuestion or '').strip() or None
    if '?' in message:
        message = message.split('?', 1)[0].strip()
        if message and not message.endswith(('.', '!', ',')):
            message += '.'
        if not message:
            message = 'Good try!'

    off_topic_patterns = (
        r'\b(capital|capital city|country|flag|largest|smallest|who is|what is the|which planet|which animal|which sport|cricket world|india\s+capital)\b',
        r'\b(what\s+is\s+the\s+capital|what\s+is\s+the\s+name\s+of|who\s+won|which\s+team|which\s+country)\b',
    )
    if follow_up:
        follow_up_lower = re.sub(r'[^a-z0-9 ]', '', follow_up.lower())
        question_words = re.sub(r'[^a-z0-9 ]', '', follow_up_lower).strip()
        sentences = re.split(r'(?<=[.!?])\s+', message)
        if sentences and re.sub(r'[^a-z0-9 ]', '', sentences[-1].lower()).strip() == question_words:
            message = ' '.join(sentences[:-1]).strip() or 'Lovely!'
        if any(re.search(pattern, follow_up_lower) for pattern in off_topic_patterns):
            follow_up = _curriculum_follow_up_question(request, follow_up)
        elif 'why' not in follow_up_lower and 'who' not in follow_up_lower and 'what' not in follow_up_lower and 'how' not in follow_up_lower:
            follow_up = _curriculum_follow_up_question(request, follow_up)

    # Do not let Julie's own fixed profile replace the learner's preference in
    # a follow-up. The lesson conversation must remain about what the child
    # just said across subsequent turns.
    conversation_text = ' '.join([*request.conversationHistory, request.studentMessage]).lower()
    student_sport = re.search(
        r"(?:my favourite sport(?: is)?|i (?:like|play))\s+(cricket|football|basketball|hockey|badminton|kho-kho)",
        conversation_text,
    )
    if follow_up and student_sport and re.search(r'\b(cricket|football|basketball|hockey|badminton|kho-kho)\b', follow_up, re.IGNORECASE):
        chosen_sport = student_sport.group(1)
        follow_up = re.sub(
            r'\b(cricket|football|basketball|hockey|badminton|kho-kho)\b',
            chosen_sport,
            follow_up,
            flags=re.IGNORECASE,
        )

    correction = result.correction
    if correction.needed and not all(value.strip() for value in (correction.original, correction.corrected, correction.explanation)):
        match = re.search(r"['\"]([A-Za-z']+)['\"]\s+should be\s+['\"]([A-Za-z']+)['\"]", message, re.IGNORECASE)
        if match:
            wrong, replacement = match.groups()
        elif re.search(r'\bgoed\b', request.studentMessage, re.IGNORECASE):
            wrong, replacement = 'goed', 'went'
        else:
            wrong = replacement = ''
        if wrong and replacement:
            corrected = re.sub(rf'\b{re.escape(wrong)}\b', replacement, request.studentMessage, count=1, flags=re.IGNORECASE)
            correction = Correction(
                needed=True,
                original=request.studentMessage,
                corrected=corrected,
                explanation=f'Use "{replacement}" instead of "{wrong}" here.',
            )

    memory_updates = list(result.memoryUpdates)
    preference = re.search(
        r"\bmy favou?rite (food|sport|subject|animal|place|festival) is ([a-z][a-z -]{0,50}?)(?:[.!?]|$)",
        request.studentMessage,
        re.IGNORECASE,
    )
    if preference:
        kind, value = preference.groups()
        key = {
            'food': 'favouriteFood',
            'sport': 'favouriteSport',
            'subject': 'favouriteSubject',
            'animal': 'favouriteAnimal',
            'place': 'favouritePlace',
            'festival': 'favouriteFestival',
        }[kind.lower()]
        if not any(update.key == key for update in memory_updates):
            memory_updates.append(MemoryUpdate(key=key, value=value.strip(), category='preference', confidence=0.95))

    follow_up_facts = [
        (r"\bi play (?:cricket|football|hockey|basketball|badminton|kho-kho) with (?:my )?([^.!?]+)", 'sportPartner'),
        (r"\bbecause (?:it is|it's|they are|they're) ([^.!?]+)", 'sportReason'),
    ]
    for pattern, key in follow_up_facts:
        match = re.search(pattern, request.studentMessage, re.IGNORECASE)
        if match and not any(update.key == key for update in memory_updates):
            memory_updates.append(MemoryUpdate(key=key, value=match.group(1).strip(), category='preference', confidence=0.9))

    unique_updates = []
    seen_memory_keys = set()
    for update in memory_updates:
        if update.key in seen_memory_keys:
            continue
        seen_memory_keys.add(update.key)
        unique_updates.append(update)

    learner_text = request.studentMessage.strip().lower()
    clarification = re.search(r"what (?:does|do) (favou?rite|subject|exciting) mean|what is the meaning of (favou?rite|subject|exciting)", learner_text)
    if clarification:
        word = next(value for value in clarification.groups() if value)
        meanings = {
            'favorite': 'Favourite means the one you like the most.',
            'favourite': 'Favourite means the one you like the most.',
            'subject': 'A subject is something you learn at school, like English or Maths.',
            'exciting': 'Exciting means something makes you feel very interested and happy.',
        }
        return result.model_copy(update={
            'message': meanings[word], 'reaction': 'encouraging',
            'followUpQuestion': _curriculum_follow_up_question(request),
            'teachingAction': 'CLARIFY', 'recommendedAction': 'CLARIFY',
            'shouldRetry': False, 'memoryUpdates': [],
        })

    if str(request.stage).upper() == 'WARM_UP':
        current = (request.currentQuestion or '').lower()
        item_match = re.search(r"(?:like|don'?t like) (?:eating |playing |doing )?([a-z ]+?)(?:[.!]|\s+or\b|$)", current)
        item = item_match.group(1).strip() if item_match else 'it'
        activity = f'eating {item}' if item in {'red chilli', 'cake'} else item
        if re.search(r"\bi no like\b|\bi not like\b", learner_text):
            model = f"I don't like {activity}."
            return result.model_copy(update={
                'message': f'I understood you! Let’s make it sound natural: “{model}”',
                'reaction': 'gentle_correction', 'followUpQuestion': None,
                'correction': Correction(needed=True, original=request.studentMessage, corrected=model, explanation='Use “I don’t like” for a negative preference.'),
                'teachingAction': 'MODEL_SENTENCE', 'recommendedAction': 'MODEL_SENTENCE',
                'modelSentence': model, 'shouldRetry': True, 'hintLevel': min(3, max(2, request.hintLevel + 1)),
                'memoryUpdates': [],
            })
        if re.search(r"\bbecause\s+(?!it is\b|it's\b)[a-z'-]+[.!]?", learner_text):
            adjective = re.sub(r'^.*\bbecause\s+|[.!?]+$', '', learner_text)
            model = f'I like {activity} because it is {adjective}.'
            return result.model_copy(update={
                'message': f'Nice idea! Make the reason complete: “{model}”',
                'reaction': 'modeling', 'followUpQuestion': None,
                'correction': Correction(needed=True, original=request.studentMessage, corrected=model, explanation='Add “it is” to complete the reason.'),
                'teachingAction': 'MODEL_SENTENCE', 'recommendedAction': 'MODEL_SENTENCE',
                'modelSentence': model, 'shouldRetry': True, 'hintLevel': min(3, max(2, request.hintLevel + 1)),
                'memoryUpdates': [],
            })
        if re.search(r"^do you like\b", learner_text):
            return result.model_copy(update={
                'message': 'I do! Cricket is exciting.', 'reaction': 'delighted',
                'followUpQuestion': f'Do you like {activity}?',
                'teachingAction': 'ACKNOWLEDGE', 'recommendedAction': 'ACKNOWLEDGE',
                'shouldRetry': False, 'memoryUpdates': [],
            })
        if re.search(r"\bi (?:don'?t )?like\b", learner_text):
            negative = bool(re.search(r"\bi don'?t like\b", learner_text))
            model = f"I {'don’t like' if negative else 'like'} {activity}."
            return result.model_copy(update={
                'message': f"{'Got it' if negative else 'Ooh, nice choice'}! You can also say: “{model}”",
                'reaction': 'curious' if negative else 'delighted', 'followUpQuestion': None,
                'teachingAction': 'ACKNOWLEDGE', 'recommendedAction': 'ACKNOWLEDGE',
                'modelSentence': model, 'shouldRetry': False, 'memoryUpdates': [],
            })

    # A learner's explicit preference is source-of-truth personal data. Keep the
    # local model from silently substituting another item in its acknowledgement.
    if preference:
        kind, raw_value = preference.groups()
        value = raw_value.strip()
        follow_ups = {
            'sport': f'Why is {value} your favourite sport?',
            'subject': f'Why is {value} your favourite subject?',
            'food': f'What do you like about {value}?',
            'animal': f'Why do you like {value}?',
            'place': f'What do you like doing at {value}?',
            'festival': f'What do you enjoy about {value}?',
        }
        return result.model_copy(update={
            'message': f'Great! Your favourite {kind.lower()} is {value}.',
            'reaction': 'encouraging',
            'followUpQuestion': follow_ups[kind.lower()],
            'correction': Correction(),
            'memoryUpdates': unique_updates[:3],
            'recommendedAction': 'CONTINUE_CONVERSATION',
            'teachingAction': 'CONTINUE_CONVERSATION',
            'modelSentence': None,
            'shouldRetry': False,
        })

    malformed_favourite_question = bool(re.fullmatch(r"what favou?rite (food|sport|subject)[?!.]?", learner_text))
    if malformed_favourite_question:
        category = re.search(r"(food|sport|subject)", learner_text).group(1)
        model = f'What is your favourite {category}?'
        return result.model_copy(update={
            'message': f'I know what you mean! Let’s make the question complete: “{model}”',
            'reaction': 'gentle_correction', 'followUpQuestion': None,
            'correction': Correction(needed=True, original=request.studentMessage, corrected=model, explanation='Add “is your” to complete the question.'),
            'teachingAction': 'MODEL_SENTENCE', 'recommendedAction': 'MODEL_SENTENCE',
            'modelSentence': model, 'shouldRetry': True,
            'hintLevel': min(3, max(2, request.hintLevel + 1)), 'memoryUpdates': [],
        })

    julie_question = any(re.search(pattern, learner_text) for pattern in (
        r"what is your favou?rite (food|sport|subject|place|animal|festival)",
        r"which (food|sport|subject|place|animal|festival) is your favou?rite",
        r"what (food|sport|subject|place|animal|festival) do you like (?:the )?most",
    ))
    if julie_question:
        category_match = re.search(r"(food|sport|subject|place|animal|festival)", learner_text)
        category = category_match.group(1) if category_match else 'sport'
        profile = {'food': 'idli', 'sport': 'badminton', 'subject': 'English', 'place': 'the library', 'animal': 'elephant', 'festival': 'Diwali'}
        return result.model_copy(update={
            'message': f'My favourite {category} is {profile[category]}!',
            'reaction': 'delighted', 'followUpQuestion': _curriculum_follow_up_question(request),
            'teachingAction': 'ACKNOWLEDGE', 'recommendedAction': 'ACKNOWLEDGE',
            'shouldRetry': False, 'memoryUpdates': [],
        })

    if re.search(r"^(do you like cartoons|do you watch cartoons|do you like games)[?!.]?", learner_text):
        return result.model_copy(update={
            'message': 'I do! Funny cartoons make me laugh.', 'reaction': 'curious',
            'followUpQuestion': _curriculum_follow_up_question(request),
            'teachingAction': 'CONTINUE_CONVERSATION', 'recommendedAction': 'CONTINUE_CONVERSATION',
            'shouldRetry': False, 'memoryUpdates': [],
        })

    # The lesson engine owns the objective, so objective-specific structural
    # omissions are deterministic even when the small local model misses them.
    target_skill = request.retryTargetSkill or next(iter(request.remainingConcepts), '')
    weak_reason = target_skill in {'sport_reason', 'subject_reason', 'give_reason'} and bool(
        re.fullmatch(r"because\s+(?!it\s+is\b|it's\b|i\b|we\b|[a-z]+\s+is\b)[a-z'-]+[.!]?", request.studentMessage.strip(), re.IGNORECASE)
    )
    if weak_reason:
        adjective = re.sub(r'^because\s+|[.!?]+$', '', request.studentMessage.strip(), flags=re.IGNORECASE)
        model = f'Because it is {adjective}.'
        return result.model_copy(update={
            'message': f"Almost! Say: “{model}”",
            'reaction': 'modeling',
            'responseQuality': 'PARTIAL',
            'followUpQuestion': None,
            'correction': Correction(needed=True, original=request.studentMessage, corrected=model, explanation='Add “it is” to complete the reason.'),
            'memoryUpdates': [],
            'recommendedAction': 'MODEL_SENTENCE',
            'teachingAction': 'MODEL_SENTENCE',
            'modelSentence': model,
            'shouldRetry': True,
            'hintLevel': min(3, max(2, request.hintLevel + 1)),
        })

    reason_improved = request.waitingForRetry and target_skill in {'sport_reason', 'subject_reason', 'give_reason'} and bool(
        re.search(r"\bbecause\s+(it is|it's|i\b|we\b|[a-z]+\s+is\b)", request.studentMessage, re.IGNORECASE)
    )
    if reason_improved:
        follow_up = _curriculum_follow_up_question(request)
        return result.model_copy(update={
            'message': 'Yesss! That is a complete reason.',
            'reaction': 'celebrating',
            'responseQuality': 'STRONG',
            'followUpQuestion': follow_up,
            'correction': Correction(),
            'recommendedAction': 'CELEBRATE_IMPROVEMENT',
            'teachingAction': 'CELEBRATE_IMPROVEMENT',
            'modelSentence': None,
            'shouldRetry': False,
            'hintLevel': request.hintLevel,
        })

    if follow_up:
        follow_up_lower = re.sub(r'[^a-z0-9 ]', '', follow_up.lower())
        if any(re.search(pattern, follow_up_lower) for pattern in off_topic_patterns):
            follow_up = _curriculum_follow_up_question(request, follow_up)
        elif 'why' not in follow_up_lower and 'who' not in follow_up_lower and 'what' not in follow_up_lower and 'how' not in follow_up_lower:
            follow_up = _curriculum_follow_up_question(request, follow_up)
    waiting_actions = {'GENTLE_CORRECTION', 'MODEL_SENTENCE', 'MODEL_FULL_SENTENCE', 'WAIT_FOR_REPEAT', 'GIVE_HINT', 'RETRY'}
    if result.teachingAction in waiting_actions or result.shouldRetry:
        follow_up = None
    elif not follow_up:
        follow_up = _curriculum_follow_up_question(request)

    # Long teacher monologues have no pedagogical benefit and make local neural
    # speech disproportionately slow. Keep the first complete reaction sentence
    # and the curriculum-controlled follow-up when Qwen exceeds the spoken cap.
    combined_words = len(f'{message} {follow_up or ""}'.split())
    if combined_words > 25:
        first_sentence = re.split(r'(?<=[.!])\s+', message, maxsplit=1)[0].strip()
        if first_sentence:
            message = first_sentence

    return result.model_copy(update={
        'message': message,
        'followUpQuestion': follow_up,
        'correction': correction,
        'memoryUpdates': unique_updates[:3],
    })


def extract_json_payload(content: str) -> str:
    cleaned = content.strip()
    if '<think>' in cleaned:
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()
    if '```' in cleaned:
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if match:
            return match.group(1).strip()
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        return match.group(0).strip()
    return cleaned


class QwenClient:
    async def status(self) -> dict[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                response = await client.get(
                    f'{settings.ollama_base_url.rstrip("/")}/api/tags'
                )
                response.raise_for_status()
                models = response.json().get('models', [])
                names = {
                    str(item.get('name') or '').strip()
                    for item in models
                    if item.get('name')
                }
                requested = settings.ollama_model.strip()
                requested_base = requested.removesuffix(':latest')
                available = any(
                    name == requested
                    or name.removesuffix(':latest') == requested_base
                    for name in names
                )
                return {'reachable': True, 'modelAvailable': available}
        except Exception:
            return {'reachable': False, 'modelAvailable': False}

    async def health(self) -> bool:
        status = await self.status()
        return status['reachable'] and status['modelAvailable']

    async def respond(self, request: BrainRequest) -> BrainResponse:
        started = time.perf_counter()
        payload = {
            'model': settings.ollama_model,
            'stream': False,
            'format': 'json',
            'messages': [
                {'role': 'system', 'content': system_prompt(request)},
                {'role': 'user', 'content': user_prompt(request)},
            ],
            'options': {
                'temperature': 0.2,
                'top_p': 0.8,
                'num_predict': 200,
                **({'num_gpu': settings.ollama_num_gpu} if settings.ollama_num_gpu is not None else {}),
            },
            'keep_alive': settings.ollama_keep_alive,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                result = None
                for attempt in range(2):
                    response = await client.post(f'{settings.ollama_base_url.rstrip("/")}/api/chat', json=payload)
                    response.raise_for_status()
                    content = response.json().get('message', {}).get('content', '')
                    cleaned_json = extract_json_payload(content)
                    try:
                        result = validate_qwen_payload(cleaned_json)
                        break
                    except Exception as parse_err:
                        logger.warning('JSON parse error on attempt %d: %s, raw: %s', attempt, parse_err, content[:150])
                        if attempt:
                            raise
                        payload['messages'] = [
                            {'role': 'system', 'content': 'Return one valid JSON object only with keys: message, reaction, followUpQuestion, correction, memoryUpdates, recommendedAction.'},
                            {'role': 'user', 'content': f'Create the short Miss Julie teacher response for Class 4 student {request.studentName} who said: "{request.studentMessage[:400]}"'},
                        ]
                if result is None:
                    raise ValueError('Qwen did not return a validated response.')
                result = normalize_response(result, request)
                logger.info('Qwen latency_ms=%d model=%s', round((time.perf_counter() - started) * 1000), settings.ollama_model)
                return result
        except Exception as exc:
            logger.exception('Qwen request failed latency_ms=%d', round((time.perf_counter() - started) * 1000))
            raise QwenUnavailable('The local Qwen teacher is unavailable or returned an invalid response.') from exc


qwen_client = QwenClient()
