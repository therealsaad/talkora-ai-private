from typing import Literal
from pydantic import BaseModel, Field


Reaction = Literal[
    'greeting', 'welcome', 'curious', 'listening', 'thinking', 'delighted',
    'encouraging', 'gentle_correction', 'modeling', 'proud', 'surprised',
    'retry', 'gentle_retry', 'hinting', 'celebrating',
]
ResponseQuality = Literal['STRONG', 'ADEQUATE', 'PARTIAL', 'UNCLEAR']
Action = Literal[
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
]


class Correction(BaseModel):
    needed: bool = False
    original: str = ''
    corrected: str = ''
    explanation: str = ''

class MemoryUpdate(BaseModel):
    key: Literal[
        'favouriteFood', 'favouriteSport', 'favouriteSubject', 'favouriteAnimal',
        'favouritePlace', 'favouriteFestival', 'sportPartner', 'sportReason', 'subjectReason',
        'hobby', 'learningStrength', 'learningNeed',
    ]
    value: str = Field(min_length=1, max_length=80)
    category: Literal['preference', 'vocabulary', 'grammar', 'pronunciation', 'speaking', 'behavior']
    confidence: float = Field(default=0.7, ge=0, le=1)


class BrainResponse(BaseModel):
    message: str = Field(min_length=1, max_length=360)
    reaction: Reaction = 'encouraging'
    responseQuality: ResponseQuality = 'ADEQUATE'
    followUpQuestion: str | None = Field(default=None, max_length=180)
    correction: Correction = Field(default_factory=Correction)
    memoryUpdates: list[MemoryUpdate] = Field(default_factory=list, max_length=3)
    recommendedAction: Action = 'CONTINUE'
    teachingAction: Action | None = None
    modelSentence: str | None = Field(default=None, max_length=300)
    activityComplete: bool = False
    shouldRetry: bool = False
    hintLevel: int = Field(default=0, ge=0, le=3)
    detectedSkills: list[str] = Field(default_factory=list, max_length=12)
    remainingSkills: list[str] = Field(default_factory=list, max_length=12)


class BrainRequest(BaseModel):
    studentName: str = Field(min_length=1, max_length=80)
    grade: int = Field(ge=4, le=10)
    avatarType: Literal['BOY', 'GIRL'] = 'BOY'
    unitNumber: int = Field(default=1, ge=1, le=8)
    unitTitle: str = Field(default='My Favourite Things', max_length=120)
    lessonTitle: str = Field(default='', max_length=120)
    stage: str = Field(default='INTERACT', max_length=40)
    activityTitle: str = Field(default='', max_length=120)
    digitalType: str = Field(default='', max_length=80)
    julieProfile: dict[str, str] = Field(default_factory=dict)
    currentQuestion: str = Field(default='', max_length=300)
    allowedVocabulary: list[str] = Field(default_factory=list, max_length=40)
    learningObjectives: list[str] = Field(default_factory=list, max_length=12)
    recentMistakes: list[str] = Field(default_factory=list, max_length=5)
    studentMemory: list[str] = Field(default_factory=list, max_length=8)
    learningEvidence: list[str] = Field(default_factory=list, max_length=12)
    conversationHistory: list[str] = Field(default_factory=list, max_length=8)
    requiredConcepts: list[str] = Field(default_factory=list, max_length=16)
    achievedConcepts: list[str] = Field(default_factory=list, max_length=16)
    remainingConcepts: list[str] = Field(default_factory=list, max_length=16)
    hintLevel: int = Field(default=0, ge=0, le=3)
    waitingForRetry: bool = False
    retryTargetSkill: str = Field(default='', max_length=80)
    recentJulieOpeners: list[str] = Field(default_factory=list, max_length=4)
    preferredExplanationLanguage: str = Field(default='English', max_length=40)
    studentMessage: str = Field(min_length=1, max_length=1000)
