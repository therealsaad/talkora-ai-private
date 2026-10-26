import unittest

from app.pronunciation.evaluator import PronunciationRequest, evaluate_speech
from app.tts.text_cleaner import clean_tts_text
from app.tts.cache import cache_key
from app.tts.parler_service import parler_service
from app.config import settings
from app.curriculum.generate_audio import fixed_lines_for_unit, available_term_one_units
from app.brain.schemas import BrainRequest, BrainResponse
from app.brain.prompts import system_prompt
from app.brain.qwen_client import validate_qwen_payload, normalize_response
from app.tts.voice_profiles import PRIYA_VOICE_ID, PRIYA_STYLE, normalize_priya_voice


class CoreServiceTests(unittest.TestCase):
    def test_brain_context_accepts_only_canonical_avatar_types(self):
        request = BrainRequest(studentName='Aanya', grade=4, avatarType='GIRL', studentMessage='I like cricket.')
        self.assertEqual(request.avatarType, 'GIRL')
        with self.assertRaises(ValueError):
            BrainRequest(studentName='Aanya', grade=4, avatarType='ROBOT', studentMessage='Hello')

    def test_tts_cleaner_removes_markdown_and_emoji(self):
        cleaned = clean_tts_text('**Wonderful!** ⭐ Try again!!!')
        self.assertNotIn('*', cleaned)
        self.assertNotIn('⭐', cleaned)
        self.assertNotIn('!!!', cleaned)

    def test_tts_cache_key_normalizes_safe_equivalent_text(self):
        args = (PRIYA_VOICE_ID, 'en-IN', PRIYA_VOICE_ID, 'indic-parler')
        self.assertEqual(cache_key('  Wonderful. ', *args), cache_key('wonderful', *args))
        self.assertEqual(cache_key('Yesss! Much better!', *args), cache_key('Yes! Much better!', *args))

    def test_priya_service_is_singleton_and_kept_resident_by_default(self):
        from app.tts.parler_service import parler_service as second_reference
        self.assertIs(parler_service, second_reference)
        self.assertFalse(settings.tts_unload_after_generation)

    def test_unit_one_prewarm_includes_common_teacher_language(self):
        lines = fixed_lines_for_unit(1)
        self.assertIn('Wonderful!', lines)
        self.assertIn('What is your favourite sport?', lines)


    def test_priya_voice_profile_keeps_compatibility_symbol_and_aliases(self):
        self.assertTrue(PRIYA_STYLE.strip())
        self.assertEqual(normalize_priya_voice('Priya'), PRIYA_VOICE_ID)
        self.assertEqual(normalize_priya_voice('talkora-priya-v2'), PRIYA_VOICE_ID)
        self.assertEqual(normalize_priya_voice('talkora-priya-v5-kids-indian'), PRIYA_VOICE_ID)
        with self.assertRaises(ValueError):
            normalize_priya_voice('random-robot-voice')

    def test_term_one_generator_detects_authored_units(self):
        self.assertEqual(available_term_one_units(), [1, 2, 3, 4])

    def test_unit_one_generator_reads_multiline_seed_prompts(self):
        lines = fixed_lines_for_unit(1)
        self.assertIn('How do you feel about playing cricket?', lines)
        self.assertIn('Look at this activity. Do you like playing cricket?', lines)

    def test_pronunciation_result_is_honest_transcript_matching(self):
        result = evaluate_speech(PronunciationRequest(
            expectedPhrase='My favourite sport is cricket',
            transcript='my favourite sport cricket',
        ))
        self.assertFalse(result['isAcousticPronunciationScore'])
        self.assertEqual(result['label'], 'Words Heard Clearly')
        self.assertIn('is', result['missingWords'])
        self.assertEqual(result['sentenceCompleteness'], 80)

    def test_teacher_prompt_requires_full_sentence_coaching_and_student_questions(self):
        prompt = system_prompt(BrainRequest(
            studentName='Aarav',
            grade=4,
            unitNumber=1,
            unitTitle='My Favourite Things',
            stage='INTERACT',
            currentQuestion='What is your favourite sport?',
            studentMessage='Cricket',
        ))
        lowered = prompt.lower()
        self.assertIn('full sentence', lowered)
        self.assertIn('student asks', lowered)
        self.assertIn('wait for the student', lowered)

    def test_qwen_payload_accepts_teaching_action_and_model_sentence_fields(self):
        payload = validate_qwen_payload('''{
            "message": "Great! Let’s say it like this: My favourite sport is cricket.",
            "reaction": "encouraging",
            "followUpQuestion": "Can you say it with me?",
            "correction": {"needed": false, "original": "", "corrected": "", "explanation": ""},
            "memoryUpdates": [],
            "recommendedAction": "WAIT_FOR_REPEAT",
            "teachingAction": "WAIT_FOR_REPEAT",
            "modelSentence": "My favourite sport is cricket.",
            "activityComplete": false,
            "detectedSkills": ["sentenceFormation"],
            "remainingSkills": ["questionFormation"]
        }''')
        self.assertEqual(payload.teachingAction, 'WAIT_FOR_REPEAT')
        self.assertEqual(payload.modelSentence, 'My favourite sport is cricket.')
        self.assertFalse(payload.activityComplete)

    def test_normalize_response_replaces_off_topic_quiz_questions_with_curriculum_questions(self):
        request = BrainRequest(
            studentName='Aarav',
            grade=4,
            unitNumber=1,
            unitTitle='My Favourite Things',
            stage='INTERACT',
            currentQuestion='What is your favourite sport?',
            studentMessage='My favourite sport is cricket.',
        )
        result = BrainResponse(
            message='Great! I like cricket too.',
            reaction='encouraging',
            followUpQuestion='What is the capital of India?',
            recommendedAction='ASK_FOLLOW_UP',
            teachingAction='ASK_FOLLOW_UP',
            modelSentence='My favourite sport is cricket.',
        )

        normalized = normalize_response(result, request)
        lowered = normalized.followUpQuestion.lower()
        self.assertNotIn('capital', lowered)
        self.assertIn('why', lowered)
        self.assertIn('favourite', lowered)

    def test_explicit_preference_cannot_be_replaced_by_model_output(self):
        request = BrainRequest(
            studentName='Aarav', grade=4, stage='INTERACT',
            currentQuestion='What is your favourite sport?',
            studentMessage='My favourite sport is cricket.',
            remainingConcepts=['sport_reason'],
        )
        result = BrainResponse(
            message='Great! My favourite sport is badminton.',
            followUpQuestion='Why do you like badminton?',
            modelSentence='My favourite sport is badminton.',
        )

        normalized = normalize_response(result, request)
        self.assertIn('cricket', normalized.message.lower())
        self.assertNotIn('badminton', normalized.message.lower())
        self.assertEqual(normalized.followUpQuestion, 'Why is cricket your favourite sport?')
        self.assertIsNone(normalized.modelSentence)

    def test_correction_action_waits_for_retry_without_new_question(self):
        request = BrainRequest(
            studentName='Aarav', grade=4, unitNumber=1,
            currentQuestion='Why do you like cricket?',
            studentMessage='Because exciting.',
        )
        result = BrainResponse(
            message='Ahaaa, almost! Say: Because it is exciting.',
            reaction='gentle_correction',
            responseQuality='PARTIAL',
            followUpQuestion='Who do you play with?',
            teachingAction='WAIT_FOR_REPEAT',
            recommendedAction='WAIT_FOR_REPEAT',
            modelSentence='Because it is exciting.',
            shouldRetry=True,
            hintLevel=3,
        )
        normalized = normalize_response(result, request)
        self.assertIsNone(normalized.followUpQuestion)
        self.assertTrue(normalized.shouldRetry)

    def test_prompt_receives_persisted_retry_context(self):
        request = BrainRequest(
            studentName='Aarav', grade=4, studentMessage='Because it is exciting.',
            waitingForRetry=True, hintLevel=3, retryTargetSkill='sport_reason',
            recentJulieOpeners=['Ahaaa', 'Lovely'],
        )
        prompt = system_prompt(request).lower()
        self.assertIn('waitingforretry', prompt)
        self.assertIn('celebrate_improvement', prompt)

    def test_incomplete_reason_deterministically_enters_model_and_retry_state(self):
        request = BrainRequest(
            studentName='Aarav', grade=4, studentMessage='Because exciting.',
            currentQuestion='Why do you like cricket?', remainingConcepts=['sport_reason'],
        )
        normalized = normalize_response(BrainResponse(message='That sounds fun.'), request)
        self.assertEqual(normalized.teachingAction, 'MODEL_SENTENCE')
        self.assertEqual(normalized.modelSentence, 'Because it is exciting.')
        self.assertTrue(normalized.shouldRetry)
        self.assertIsNone(normalized.followUpQuestion)

    def test_improved_reason_is_celebrated_and_moves_to_nearby_skill(self):
        request = BrainRequest(
            studentName='Aarav', grade=4, studentMessage='Because it is exciting.',
            waitingForRetry=True, retryTargetSkill='sport_reason', hintLevel=2,
            remainingConcepts=['favourite_subject'],
        )
        normalized = normalize_response(BrainResponse(message='Okay.'), request)
        self.assertEqual(normalized.teachingAction, 'CELEBRATE_IMPROVEMENT')
        self.assertFalse(normalized.shouldRetry)
        self.assertEqual(normalized.followUpQuestion, 'What is your favourite subject?')

    def test_julie_answers_natural_question_from_stable_profile(self):
        request = BrainRequest(studentName='Aarav', grade=4, studentMessage='Which food is your favourite?', remainingConcepts=['ask_favourite_sport'])
        normalized = normalize_response(BrainResponse(message='Okay.'), request)
        self.assertEqual(normalized.message, 'My favourite food is idli!')

    def test_malformed_favourite_question_waits_for_retry_before_answer(self):
        request = BrainRequest(studentName='Aarav', grade=4, studentMessage='What favourite food?')
        normalized = normalize_response(BrainResponse(message='Okay.'), request)
        self.assertTrue(normalized.shouldRetry)
        self.assertEqual(normalized.modelSentence, 'What is your favourite food?')
        self.assertIsNone(normalized.followUpQuestion)

    def test_clarification_is_explained_then_returns_to_lesson(self):
        request = BrainRequest(studentName='Aarav', grade=4, studentMessage='What does favourite mean?', remainingConcepts=['favourite_subject'])
        normalized = normalize_response(BrainResponse(message='Okay.'), request)
        self.assertIn('one you like the most', normalized.message)
        self.assertEqual(normalized.followUpQuestion, 'What is your favourite subject?')

    def test_mild_off_topic_question_is_briefly_answered_and_redirected(self):
        request = BrainRequest(studentName='Aarav', grade=4, studentMessage='Do you like cartoons?', remainingConcepts=['favourite_subject'])
        normalized = normalize_response(BrainResponse(message='Okay.'), request)
        self.assertIn('cartoons', normalized.message.lower())
        self.assertEqual(normalized.followUpQuestion, 'What is your favourite subject?')

    def test_warmup_stays_on_active_item_and_corrects_negative_form(self):
        request = BrainRequest(studentName='Aarav', grade=4, stage='WARM_UP', currentQuestion="Say: I like eating red chilli. or I don't like eating red chilli.", studentMessage='I no like chilli.')
        normalized = normalize_response(BrainResponse(message='Let us cook something.'), request)
        self.assertTrue(normalized.shouldRetry)
        self.assertEqual(normalized.modelSentence, "I don't like eating red chilli.")
        self.assertIsNone(normalized.followUpQuestion)

    def test_warmup_natural_answer_gets_short_item_specific_reaction(self):
        request = BrainRequest(studentName='Aarav', grade=4, stage='WARM_UP', currentQuestion='Say: I like eating red chilli.', studentMessage='I like red chilli.')
        normalized = normalize_response(BrainResponse(message='Long unrelated response.'), request)
        self.assertFalse(normalized.shouldRetry)
        self.assertIn('red chilli', normalized.message.lower())
        self.assertIsNone(normalized.followUpQuestion)

    def test_follow_up_keeps_the_students_sport_across_turns(self):
        request = BrainRequest(
            studentName='Aarav', grade=4,
            currentQuestion='Why do you like cricket?',
            conversationHistory=['Aarav: My favourite sport is cricket.'],
            studentMessage='I like it because I play with my friends.',
        )
        result = BrainResponse(message='Great reason!', followUpQuestion='Why do you like badminton?')
        normalized = normalize_response(result, request)
        self.assertEqual(normalized.followUpQuestion, 'Why do you like cricket?')


if __name__ == '__main__':
    unittest.main()
