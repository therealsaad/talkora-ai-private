# Authorized curriculum context v1

The existing `/v1/brain/respond` route now optionally consumes `teachingContext`
from the authenticated Node backend. This is a bounded data/support contract for
the already authored Class 1 `g01-l01` school-action and poem scenes. It does not
open KG6–10, another grade, lesson publication or progress writes.

Node projects its authorized Activity/Lesson records into exact current lines,
stable line IDs, source citation, objective, vocabulary, bilingual hints and a
deterministic current-activity support plan. Missing source identity remains
unknown. The Python schema rejects mixed grade/lesson/scene/question/vocabulary,
unknown/altered poem ranges, versions, over-budget text and extra authority
fields. It never treats a citation or support mode as a publication/grade flag.

Routine responses use the supplied English model and optional stored hints with
the existing reviewed fallback. They do not contact Ollama. Novel questions use
the existing local 1.8-second Qwen budget with current-line/source/objective and
support data; malformed, unsafe or unavailable model output keeps the reviewed
fallback. Child speech/history are untrusted data. The legacy tiny-word guard
cannot overwrite the validated current model. All responses retain
`activityComplete: false`, empty verified memory/skills and Node-owned grading.

Support modes: MODEL supplies an example, GUIDE one hint, PRACTISE rehearses,
CHECK invites independent recall on the same objective. They come from saved
current-activity evidence/retry state and do not prove current success, accent,
pronunciation, IQ or mastery. New coaching wording still needs educator/native
speaker review and real microphone/speaker acceptance before school release.

`tests/fixtures/class1-teaching-context-v1.json` is identical to the app fixture
and is tested through the real ASGI route. Tests cover the recorded `At at.`
poem mismatch, Hindi/Marathi hints, data-only model changes, malformed/forged
context, injection, recall, Qwen timeout/output rejection, service keys and old
Node requests. Run the normal offline suite:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 TALKORA_ENV=test python -m pytest -q tests
```

No model download, fine-tune, paid call, live pupil test, database operation,
curriculum publication, voice replacement or deployment occurred. New Python
accepts old Node requests; deploy the reviewed Python consumer before the Node
producer for the new behavior. Reverting code needs no student-data rollback.
The app's `docs/class1-db-teaching-context-2026-11-11.md` includes the producer,
authoring fields and optional real Node → owned loopback Python verification.
The obsolete `qwen-service` is not used.
