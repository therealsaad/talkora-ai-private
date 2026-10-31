"""Opt-in loopback demonstration. Never imported by server.main or compat."""
import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from server.bridge_security import is_production, require_bridge_key
from server.compat import router as legacy_router
from server.teaching import Registry, Strategy, Turn, decide, normalize, Observation
from .coach import GenerativeCoach
from .fixtures import KEY, objective


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    namespace: str = Field(min_length=1, max_length=80)
    bookId: str = Field(min_length=1, max_length=80)
    edition: str = Field(min_length=1, max_length=80)
    trackId: str = Field(min_length=1, max_length=80)
    lessonId: str = Field(min_length=1, max_length=80)
    activityId: str = Field(min_length=1, max_length=80)
    objectiveId: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)

    def key(self):
        return (self.namespace, self.bookId, self.edition, self.trackId,
                self.lessonId, self.activityId, self.objectiveId, self.version)


class TeachingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contractVersion: Literal["teaching.dev.v1"]
    sessionId: UUID
    requestId: UUID
    expectedRevision: int = Field(ge=0, le=64, strict=True)
    scope: Scope
    event: Literal["INTRODUCE", "ANSWER", "HINT", "EXPLAIN", "RECALL"]
    transcript: str = Field(default="", max_length=300)
    inputStatus: Literal["TEXT", "SPEECH", "SILENCE", "STT_FAILED", "NO_MIC"] = "TEXT"
    language: Literal["en", "hi", "mr"] = "en"


@dataclass
class Session:
    key: tuple
    created: float = field(default_factory=time.monotonic)
    revision: int = 0
    mistakes: int = 0
    supplies_answer: bool = False
    prior: Strategy | None = None
    last_answer_digest: str | None = None
    results: dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def development_access(request: Request):
    if production_environment() or os.getenv("TALKORA_ENABLE_TEACHING_HARNESS") != "true":
        raise HTTPException(404, "Development harness disabled")
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Loopback clients only")
    if len(os.getenv("TALKORA_SERVICE_KEY", "")) < 32:
        raise HTTPException(503, "Development service authentication required")
    await require_bridge_key(request)


def production_environment():
    return is_production() or any(os.getenv(name, "").strip().lower() == "production"
                                  for name in ("TALKORA_ENV", "ENVIRONMENT", "NODE_ENV"))


def create_app(*, coach=None):
    if production_environment() or os.getenv("TALKORA_ENABLE_TEACHING_HARNESS") != "true":
        raise RuntimeError("Explicit non-production harness opt-in required")
    app = FastAPI(title="SYNTHETIC Miss Julie development harness", docs_url=None,
                  redoc_url=None, openapi_url=None, dependencies=[Depends(development_access)])
    # Real compatibility handler, unchanged. It still enforces its pilot/grade/
    # language/security gates. This is a separate ASGI app, never the live one.
    app.include_router(legacy_router)
    engine = coach or GenerativeCoach()
    registry = Registry((objective(),), allow_synthetic=True)
    sessions = {}

    @app.get("/health")
    async def health():
        return {"status": "ok", "developmentOnly": True, "syntheticOnly": True,
                "entrypoint": "dev_harness.app:create_app", "productionIntegration": False}

    @app.post("/dev/teaching/turn")
    async def teaching(req: TeachingRequest):
        started = time.perf_counter()
        key = req.scope.key()
        if key[:-1] == KEY[:-1] and key[-1] != KEY[-1]:
            raise HTTPException(409, "Stale synthetic curriculum version")
        if key[4] != KEY[4]:
            raise HTTPException(404, "Unknown synthetic lesson")
        if key != KEY:
            raise HTTPException(403, "Scope is not authorized by the harness fixture grant")
        current_objective = registry.resolve(key, grade=1, authorized_keys=frozenset((KEY,)))
        now = time.monotonic()
        for session_id in list(sessions):
            if now - sessions[session_id].created > 1200 and not sessions[session_id].lock.locked():
                del sessions[session_id]
        sid = str(req.sessionId)
        if sid not in sessions:
            if req.expectedRevision != 0:
                raise HTTPException(409, "No resumable development session")
            if len(sessions) >= 64:
                raise HTTPException(429, "Development session limit")
            sessions[sid] = Session(key)
        session = sessions[sid]
        digest = hashlib.sha256(req.model_dump_json().encode()).hexdigest()
        async with session.lock:
            rid = str(req.requestId)
            if rid in session.results:
                prior_digest, response = session.results[rid]
                if digest != prior_digest:
                    raise HTTPException(409, "Idempotency key reused for a different payload")
                return response
            if session.key != key or req.expectedRevision != session.revision:
                raise HTTPException(409, "Stale or mismatched development session")
            if session.revision >= 64:
                raise HTTPException(429, "Development turn limit")
            turn = Turn(transcript=req.transcript, input_status=req.inputStatus, language=req.language,
                        supported=session.supplies_answer, prior_strategy=session.prior, mistakes=session.mistakes)
            decision = decide(current_objective, turn)
            strategy = decision.strategy.value
            unavailable = req.inputStatus in ("SILENCE", "STT_FAILED", "NO_MIC") or (req.event == "ANSWER" and not req.transcript.strip())
            if unavailable:
                strategy = "LISTEN"
            elif decision.observation == Observation.OFF_TOPIC and req.event == "ANSWER":
                strategy = "REDIRECT"
            elif req.event in ("INTRODUCE", "EXPLAIN"):
                strategy = "EXPLAIN" if session.prior != Strategy.EXPLAIN else "RETEACH"
            elif req.event == "HINT":
                strategy = "GUIDE"
            elif req.event == "RECALL":
                # This fixture has no scheduled retention rubric. No recall proof.
                strategy = "INDEPENDENT_CHECK"
            # Native-language meanings are supported conceptual observations,
            # never independent English production. No raw words enter Qwen.
            native = normalize(req.transcript) in {normalize(x) for x in ("नीचे", "खाली")}
            if native and not unavailable:
                strategy = "GUIDE"
            signal = "SUPPORT_LANGUAGE_MEANING" if native else decision.observation.value
            if req.event == "ANSWER" and normalize(req.transcript) == "on" and not unavailable:
                signal = "LEXICAL_MISMATCH_ON"
            next_mistakes = session.mistakes
            if req.event == "ANSWER" and decision.observation == Observation.MISMATCH:
                next_mistakes += 1
                if next_mistakes >= 2:
                    strategy = "RETEACH"
            response = await engine.respond(strategy, req.language, signal)
            independent = strategy in ("INDEPENDENT_CHECK", "RECALL")
            session.supplies_answer = strategy != "LISTEN" and not independent
            session.prior = Strategy.ASK if strategy == "REDIRECT" else Strategy(strategy)
            session.mistakes = next_mistakes
            session.revision += 1
            support = "SUPPORTED" if native else decision.answer_support
            answer_digest = hashlib.sha256(normalize(req.transcript).encode()).hexdigest()
            if req.event == "ANSWER" and decision.observation == Observation.MATCH:
                if session.last_answer_digest == answer_digest:
                    support = "SUPPORTED"  # Repeating a prior answer is still not independence.
                session.last_answer_digest = answer_digest
            advisory = {
                "contractVersion": "teaching.dev.v1", "synthetic": True, "scope": req.scope.model_dump(),
                "sessionId": sid, "requestId": rid, "revision": session.revision,
                "strategyCandidate": strategy, "lexicalObservation": signal, "answerSupport": support,
                "validatedLearning": False, "acceptedEvidence": [], "independentCheckRequested": independent,
                "suppliesAnswer": session.supplies_answer, "providerStatus": response.status,
                "rejectionReason": response.rejection_reason,
                "targetAnchored": response.target_anchored,
                "wordingSource": "qwen-generated" if response.status == "generated" else "reviewed-fallback",
                "latency": {"providerMs": response.elapsed_ms,
                            "bridgeMs": round((time.perf_counter() - started) * 1000, 3)},
            }
            # Draft optional-extension preview only. Existing live handler is
            # unchanged. UNCLEAR is fixed, never a lexical-to-success mapping.
            result = {"message": response.message, "reaction": "encouraging", "responseQuality": "UNCLEAR",
                      "followUpQuestion": response.question,
                      "correction": {"needed": False, "original": "", "corrected": "", "explanation": ""},
                      "memoryUpdates": [], "recommendedAction": "ASK_FOLLOW_UP", "teachingAction": "ASK_FOLLOW_UP",
                      "modelSentence": None, "activityComplete": False, "shouldRetry": False,
                      "hintLevel": 1 if session.supplies_answer else 0, "detectedSkills": [], "remainingSkills": [],
                      "teaching": advisory}
            session.results[rid] = (digest, result)
            return result

    return app
