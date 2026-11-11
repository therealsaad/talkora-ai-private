"""Bounded curriculum data supplied only through the authenticated Node bridge.

Version 1 consumes the existing First Day scenes. It cannot enable another
grade, publish a lesson, evaluate mastery or write student state.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from .class1_first_day import POEM_SCENES, POEM_SCENE_KEYS


class StrictData(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class LessonSource(StrictData):
    reference: str | None = Field(max_length=300)
    label: str | None = Field(max_length=240)
    book: str | None = Field(max_length=160)
    edition: str | None = Field(max_length=40)
    chapter: str | None = Field(max_length=60)
    pageStart: int | None = Field(ge=1)
    pageEnd: int | None = Field(ge=1)


class LessonHints(StrictData):
    en: str | None = Field(max_length=240)
    hi: str | None = Field(max_length=240)
    mr: str | None = Field(max_length=240)


class LessonSupport(StrictData):
    mode: Literal['MODEL', 'GUIDE', 'PRACTISE', 'CHECK']
    hintLevel: int = Field(ge=0, le=3)
    reason: Literal['FIRST_ATTEMPT', 'RETRY', 'REPEATED_DIFFICULTY',
                    'SUPPORTED_ATTEMPT', 'INDEPENDENT_EVIDENCE']
    recentAttempts: int = Field(ge=0, le=8)


SCENE_FOCUS = {
    'hello-school': 'school', 'skip-bunny': 'skip', 'run-race': 'run',
    'walk-school': 'walk', 'big-grin': 'smile', 'school-bell': 'bell',
    'jump-frog': 'jump', 'play-friends': 'play', 'enter-class': 'classroom',
    'grade-one': 'grade one', 'poem-pair-1': 'skip', 'poem-pair-2': 'school',
    'poem-pair-3': 'smile', 'poem-pair-4': 'jump', 'poem-pair-5': 'grade one',
    'poem-full': 'school',
}


class LessonTeachingContext(StrictData):
    version: Literal[1]
    grade: Literal[1]
    lessonKey: Literal['g01-l01']
    sceneKey: str = Field(min_length=1, max_length=32)
    activityKey: str = Field(min_length=1, max_length=96)
    revision: str = Field(min_length=1, max_length=120)
    mode: Literal['SCHOOL_ACTION', 'RECITE']
    learnerBand: Literal['EARLY_PRIMARY']
    focus: Literal['school', 'skip', 'run', 'walk', 'smile', 'bell', 'jump',
                   'play', 'classroom', 'grade one']
    source: LessonSource
    objective: str = Field(min_length=1, max_length=240)
    teacherQuestion: str = Field(min_length=1, max_length=1400)
    lineIds: list[str] = Field(min_length=1, max_length=10)
    modelLines: list[str] = Field(min_length=1, max_length=10)
    vocabulary: list[str] = Field(max_length=32)
    hints: LessonHints
    support: LessonSupport

    @model_validator(mode='before')
    @classmethod
    def reject_boolean_versions(cls, value):
        if isinstance(value, dict) and (type(value.get('version')) is not int or type(value.get('grade')) is not int):
            raise ValueError('Numeric curriculum version/grade required')
        return value

    @model_validator(mode='after')
    def validate_current_scene(self):
        poem = self.sceneKey.startswith('poem-')
        if SCENE_FOCUS.get(self.sceneKey) != self.focus:
            raise ValueError('Unapproved scene/focus')
        if self.activityKey != f'class1-l01-{"v4" if poem else "v3"}-{self.sceneKey}':
            raise ValueError('Activity/scene mismatch')
        if self.mode != ('RECITE' if poem else 'SCHOOL_ACTION'):
            raise ValueError('Teaching mode mismatch')
        count = 10 if self.sceneKey == 'poem-full' else 2 if poem else 1
        if len(self.modelLines) != count or len(self.lineIds) != count:
            raise ValueError('Wrong current-line range')
        for values, limit in ((self.modelLines, 160), (self.lineIds, 96), (self.vocabulary, 40)):
            if any(not value or len(value) > limit or
                   any(ord(char) < 32 or ord(char) == 127 for char in value) for value in values):
                raise ValueError('Invalid curriculum text')
        if len(set(self.lineIds)) != count:
            raise ValueError('Duplicate current line')
        offset = 0 if self.sceneKey == 'poem-full' or not poem else (int(self.sceneKey[-1]) - 1) * 2
        if self.lineIds != [f'g01-l01:{self.sceneKey}:line-{offset + index + 1}' for index in range(count)]:
            raise ValueError('Wrong current line identity')
        if poem:
            models = ([POEM_SCENES[POEM_SCENE_KEYS[f'poem-pair-{i}']][1] for i in range(1, 6)]
                      if self.sceneKey == 'poem-full' else [POEM_SCENES[POEM_SCENE_KEYS[self.sceneKey]][1]])
            words = lambda value: re.findall(r'[a-z]+', value.lower())
            if words(' '.join(self.modelLines)) != words(' '.join(models)):
                raise ValueError('Poem differs from the authored current scene')
        if len(json.dumps(self.model_dump(), ensure_ascii=False, separators=(',', ':'))) > 6000:
            raise ValueError('Teaching context exceeds the bridge budget')
        return self


def current_teaching_context(req: Any) -> LessonTeachingContext | None:
    """Reject mismatched new payloads; older Node requests keep the old path."""
    value = getattr(req, 'teachingContext', None)
    if value is None:
        return None
    try:
        context = value if isinstance(value, LessonTeachingContext) else LessonTeachingContext.model_validate(value)
    except ValidationError as exc:
        raise HTTPException(422, 'INVALID_LESSON_TEACHING_CONTEXT') from exc
    if (req.grade != context.grade or req.levelId != context.lessonKey or
            getattr(req, 'sceneKey', '') != context.sceneKey or
            req.currentQuestion != context.teacherQuestion or
            set(req.allowedVocabulary) != set(context.vocabulary)):
        raise HTTPException(422, 'LESSON_TEACHING_CONTEXT_MISMATCH')
    return context


def teaching_prompt_data(context: LessonTeachingContext) -> dict[str, Any]:
    """Curriculum/support only. No learner identity, token, answer or transcript."""
    return {
        'schema_version': context.version, 'source': context.source.model_dump(),
        'scene_key': context.sceneKey, 'objective': context.objective,
        'learner_band': context.learnerBand, 'line_ids': context.lineIds,
        'approved_lines': context.modelLines, 'allowed_vocabulary': context.vocabulary,
        'support': context.support.model_dump(),
    }
