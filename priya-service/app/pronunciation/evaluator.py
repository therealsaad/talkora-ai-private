import re
from difflib import SequenceMatcher
from pydantic import BaseModel, Field


class PronunciationRequest(BaseModel):
    expectedPhrase: str = Field(min_length=1, max_length=500)
    transcript: str = Field(default='', max_length=1000)
    durationSeconds: float | None = Field(default=None, ge=0, le=120)
    confidence: float | None = Field(default=None, ge=0, le=1)


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def evaluate_speech(request: PronunciationRequest) -> dict:
    expected = tokens(request.expectedPhrase)
    heard = tokens(request.transcript)
    matcher = SequenceMatcher(a=expected, b=heard)
    word_results = [{'word': word, 'heardClearly': False} for word in expected]
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            word_results[block.a + offset]['heardClearly'] = True
    missing = [item['word'] for item in word_results if not item['heardClearly']]
    extra = [heard[index] for tag, _, _, start, end in matcher.get_opcodes() if tag in ('insert', 'replace') for index in range(start, end)]
    correct = [item['word'] for item in word_results if item['heardClearly']]
    wrong = [heard[index] for tag, _, _, start, end in matcher.get_opcodes() if tag == 'replace' for index in range(start, end)]
    heard_count = sum(1 for item in word_results if item['heardClearly'])
    completeness = round(heard_count / max(1, len(expected)) * 100)
    similarity = round(matcher.ratio() * 100)
    pace = None
    if request.durationSeconds and request.durationSeconds > 0:
        pace = round(len(heard) / request.durationSeconds * 60)
    if not heard:
        feedback = 'I could not hear the words yet. Move a little closer and try once more.'
    elif missing:
        feedback = f"Great try! Say '{missing[0]}' a little more clearly. Listen once and try again."
    else:
        feedback = 'Wonderful! I heard every word in the sentence clearly.'
    return {
        'label': 'Words Heard Clearly',
        'wordsHeardClearly': heard_count,
        'expectedWordCount': len(expected),
        'sentenceCompleteness': completeness,
        'sentenceSimilarity': similarity,
        'correctWords': correct,
        'wrongWords': wrong,
        'missingWords': missing,
        'extraWords': extra,
        'wordOrderMatched': matcher.ratio() == 1,
        'speakingPaceWpm': pace,
        'sttConfidence': request.confidence,
        'wordResults': word_results,
        'feedback': feedback,
        'isAcousticPronunciationScore': False,
    }
