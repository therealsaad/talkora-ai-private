# Miss Julie advisory teaching brain — Issue #13

Implemented in `server/teaching.py` in **therealsaad/talkora-ai-private**.
This is callable Python teaching intelligence with offline tests, not a new Node
engine, deployed service or approved shared API. No existing route is rewired.

## Service reconciliation

- Base: latest fetched AI `origin/main`, `ff81abe9bc4debdc3446f51fc4dced6b63078dbd`.
- Isolated branch/worktree: `feature/miss-julie-ai-brain-v1`,
  `D:\talkora-ai-brain-v1`. Original AI checkout `D:\talkora-ai-publish`
  was clean and remains unchanged. `talkor` is read-only throughout this task.
- Node's `PythonAIProvider` calls `/v1/brain/respond`; authorized Class 1
  `g01-l01` defaults to port 8002. KG feedback also defaults to 8002 with a
  seven-second deadline. General Node AI service defaults to 8001 and is a
  separate configuration path, not proof that the 8002 package is active.
- Launch instructions identify `python -m uvicorn server.main:app` from
  `talkora-ai-starter`. This package contains the newer Class 1 adaptive,
  full-poem coaching, language resolution, response guards and bridge security.
  `qwen-service` is an older source snapshot whose startup assumes an untracked
  seed. It is not interchangeable with this package. `priya-service` is separate
  and untouched.
- No port-8002 listener/process was observable at inspection. The historical
  `ai-models/talkora-ai-starter` directory exists, but its `class1_adaptive.py`
  hash differs from this repository. **The currently deployed process and source
  parity could not be established.** Confirm deployment working directory,
  executable, revision and environment before rollout; do not copy over local code.
- Existing training scripts generate synthetic examples or offer separately
  gated QLoRA research. Their 1.7B research base is not the running 4B Ollama
  model. No training, model downloads, dataset changes or model deployment occurred.

## What the code does

`Registry` resolves exact lesson/activity/objective/version and grade against
trusted caller-supplied authorization. Unknown, unauthorized, unreviewed or
missing objectives fail closed. It rejects synthetic curriculum unless explicitly
enabled for tests. The internal `Objective` adapter records a review reference;
it does not replace Z.ai's schema or establish authenticity by itself. Never
construct the registry or authorization set from client-provided extra fields.

`observe` produces conservative exact-match, partial, mismatch, ambiguous,
unavailable or off-topic **lexical observations**. This is not a semantic
correctness oracle or an acoustic pronunciation assessment. Non-exact bilingual
answers need a reviewed rubric/Node evaluator; they do not imply English mastery.

`decide` selects diagnose, explain, model, ask, guide, listen, gentle correction,
reteach, independent check, revision or recall. Repeated difficulties rotate
reviewed alternative explanations without GPU calls; repeated exhaustion offers
revision. A repeated/hinted/model-contaminated match is SUPPORTED. Even an
unprompted exact match is only UNVERIFIED_INDEPENDENT and requests another check.
Recall is requested only for objectives requiring it when trusted context says
it is due. No strategy accepts evidence, completes a lesson or unlocks anything.

Cards contain curriculum-owner-authored wording alternatives and questions for
each offered strategy/language. A missing language fails closed rather than
silently substituting a language. Existing Hindi/Marathi preference resolution
is reused; learning examples remain in the reviewed cards. Grade-specific
content and KG/Class 1 length limits prevent automatic reuse of young-child
wording for older grades. Independent/recall cards cannot contain model answers
or reveal exact rubric answers. A reference and lexical checks are not a
substitute for educator safety, language and curricular review of the cards.

`QwenWordingSelector` can choose only an integer index into those approved
alternatives. Arbitrary model explanations, unknown keys, invalid types,
oversized output and progress assertions are rejected. Its prompt contains only
grade, strategy, observation, language and reviewed wording candidates: **no
student transcript, identity, PIN, history, private memory, secrets or audio**.
Qwen receives no tools. It cannot invent a question or change strategy.

Only local Ollama localhost/127.0.0.1:11434 is permitted. One wall-clock deadline
(default four seconds, configurable up to six) includes at most two transport
attempts. Only transient transport/5xx failures get one retry; malformed JSON and
4xx are not retried. Streamed upstream output is bounded before parsing. Parent
cancellation propagates. Failures use the selected-language reviewed wording,
never another provider or success evidence. Unavailable/off-topic input and
repeated difficulties skip inference. No mutable student sessions are retained.

The existing Class 1 poem coach intentionally fails closed on provider outages;
its behavior and approval gates are unchanged. This isolated module's fallback
must not be substituted into that live path without release review.

## Internal example (synthetic fixture only)

For a synthetic animal objective, `dog` when the reviewed lexical answer is `cat`
produces an advisory CORRECT strategy and the following legacy-shaped preview:

```json
{
  "message": "Good effort. Listen: cat.",
  "reaction": "encouraging",
  "responseQuality": "PARTIAL",
  "followUpQuestion": "Which animal makes this sound?",
  "correction": {"needed": false, "original": "", "corrected": "", "explanation": ""},
  "memoryUpdates": [],
  "recommendedAction": "GENTLE_CORRECTION",
  "teachingAction": "GENTLE_CORRECTION",
  "modelSentence": null,
  "activityComplete": false,
  "shouldRetry": true,
  "hintLevel": 1,
  "detectedSkills": [],
  "remainingSkills": []
}
```

`Guidance.legacy_response()` exists for review/tests, not HTTP activation.
The response preview asserts no authoritative correctness, mastery, XP,
unlocking or new shared fields. `hintLevel` describes support in the returned
wording, not a persisted count. All generated observations and action candidates
remain advisory even when their names resemble legacy action names.

## Application-side integration requirements — approval still required

1. Confirm the deployed 8002 package/revision; do not replace `qwen-service`,
   `priya-service` or the historical local starter folder based on a name alone.
2. Z.ai supplies reviewed objectives, rubric mappings, age-appropriate cards and
   en/hi/mr scaffolds. No official curriculum or production registry is invented
   here. Synthetic fixtures exist only in `tests/test_teaching.py`.
3. Node resolves authorization, objective/version and structured STT status;
   supplies objective-scoped support/examples, retry context and recall scheduling;
   persists that context and handles per-student concurrency/idempotency. This
   Python module is stateless. Its match observations must never be accepted as
   independent correctness or mastery by default.
4. Project Manager reviews any proposed optional `teachingSuggestion` response
   extension (strategy, observation, support provenance, advisory-only marker).
   **No such field is added or enabled here.** Current `/v1/brain/respond`
   request/response fields, pilot gates, route allowlists and service-key
   authentication are unchanged. New grades remain unavailable over HTTP.
5. An approved adapter may call `TeachingBrain.respond` server-side and map its
   wording to existing fields. Keep existing Class 1 scene/poem guards until an
   explicit integration decision. Recheck Node interpretation of legacy
   `responseQuality`, `shouldRetry`, `hintLevel` and action strings before use.
6. Node continues to own authoritative evaluation, accepted evidence, mandatory
   intros, speech ACKs, student sessions, progress, XP, completion and unlocking.
   Audio outages remain unavailable evidence. Azure is untouched; a successful
   brain test says nothing about live Azure or end-to-end classroom behavior.

## Verification

From `talkora-ai-starter`, using an isolated Python 3.12 venv and existing API
requirements plus pytest:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
..\.venv\Scripts\python.exe -m pytest -q tests
```

Final result: **117 passed, 1 skipped** (one dependency warning about Starlette's
httpx-based TestClient). `python -m compileall -q server` also passed. The suite includes existing
Class 1/bilingual/poem/security tests plus new strategy, contamination, registry,
malformed/unsafe model, bounded retry/timeout/cancellation, privacy, language,
grade and unchanged route contract tests. All model fault paths use
`httpx.MockTransport`; they are not live inference validation. The optional
untracked experimental `/chat` seed test is skipped when that seed is absent.

Manual source startup: a disposable `uvicorn server.main:app` process on 18082
returned `/health` HTTP 200 with an empty optional lesson registry, then was
stopped. No existing process was replaced. Local `/api/tags` reported the existing
`qwen3:4b-instruct` model. A synthetic live selector request used its six-second
budget and returned reviewed fallback after 6.02 seconds: **model wording quality
and successful inference within the deadline are not verified**. No Azure calls,
GPU training, load benchmark or full separate Priya/older-qwen regression run is
claimed. No live raw child data was sent.
