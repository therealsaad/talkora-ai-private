# Issue #15: isolated Miss Julie teaching bridge

**Development-only; synthetic curriculum; draft contract; no deployment.**
This work is stacked on AI PR #14 (`f42b4b9`) because that dependency remains
unmerged. The separate Issue #15 PR targets `feature/miss-julie-ai-brain-v1` so
reviewers see only the harness changes. Retarget after dependency review; do not
merge either PR or enable production routes without PM approval.

## What is actually demonstrated

The separate ASGI application includes the **unchanged** compatibility router,
and proves an authenticated `/v1/brain/respond` Class 1 word-repeat request over
real loopback HTTP. Its `/dev/teaching/turn` endpoint then demonstrates a
synthetic positional-language task: explanation, a wrong lexical response,
gentle correction, roof-analogy reteaching, a hint, a supported response and an
independent-check request. Qwen generates fresh message/question strings from
facts and strategy, **not an index into prepared variants**.

All curriculum identities start with `synthetic`; no book or official rubric is
invented. English, Hindi and Marathi fixture facts/scaffolds are test-only, not
teacher-approved lessons. Hindi/Marathi meanings count as supported observations,
not independent English production. A lexical match, repeated answer or model
explanation never establishes comprehension, retention, pronunciation or mastery.

## Reproduce the full demonstration

Install the existing `requirements.txt` plus pytest in an isolated environment.
Use the already installed local model; the demo never downloads or unloads it.
From `talkora-ai-starter`:

```powershell
python -m dev_harness.demo --port 18152 --output demo.json
```

The runner checks that the port is free, creates a fresh random service key in
the child environment, starts its own server, exercises the real legacy handler
and varied generative turns, writes **synthetic** evidence/latencies, and stops
only its own process in `finally`. Keys are not printed or written to the report.
It probes 8002 without changing it. Startup failures/occupied ports are errors;
it does not attach to an unknown server or stop another process.

The first harness call tests cold-model recovery if the model is naturally
unloaded. Then a separate raw synthetic Qwen call (90-second measurement budget,
not a student-turn budget) measures actual load/generation and warms the model.
It follows with varied English/Hindi/Marathi strategy turns. Natural warm/cold
state is reported truthfully; the script never forces a cold state.

For an interactive developer run:

```powershell
$env:TALKORA_ENV='development'
$env:TALKORA_ENABLE_TEACHING_HARNESS='true'
# Supply a fresh random key of at least 32 characters through the environment.
$env:TALKORA_SERVICE_KEY='<development-only-random-key>'
$env:TALKORA_CLASS1_QWEN_PILOT='true'
python -m dev_harness --port 18152
```

Send `X-Talkora-Service-Key` on every request. The launcher binds only 127.0.0.1,
allows ports 18000–18999, and never uses port 8002. The app independently rejects
non-loopback clients, missing/short keys, disabled opt-in and production
environments. Its OpenAPI/docs routes are disabled. This is server-to-server
development authentication, **not student authentication**.

## Draft optional teaching extension

Not an approved shared API. No fields or routes were added to `server.main`,
`server.compat`, the deployed service or `talkor`. Only the development endpoint
returns this proposed extension beside the existing legacy field names.

Example request to `/dev/teaching/turn` (UUIDs are anonymous developer IDs):

```json
{
  "contractVersion": "teaching.dev.v1",
  "sessionId": "00000000-0000-4000-8000-000000000001",
  "requestId": "00000000-0000-4000-8000-000000000002",
  "expectedRevision": 0,
  "scope": {
    "namespace": "synthetic", "bookId": "position-fixture", "edition": "test-only",
    "trackId": "demo", "lessonId": "positions", "activityId": "under",
    "objectiveId": "below-relation", "version": "v1"
  },
  "event": "INTRODUCE", "transcript": "", "inputStatus": "TEXT", "language": "en"
}
```

Response excerpt (other legacy fields remain present):

```json
{
  "message": "Under means below something. The ball is under the box.",
  "followUpQuestion": "Which position word fits?",
  "responseQuality": "UNCLEAR", "activityComplete": false,
  "memoryUpdates": [], "detectedSkills": [],
  "teaching": {
    "contractVersion": "teaching.dev.v1", "synthetic": true,
    "revision": 1, "strategyCandidate": "EXPLAIN",
    "lexicalObservation": "UNAVAILABLE", "answerSupport": "UNKNOWN",
    "validatedLearning": false, "acceptedEvidence": [],
    "independentCheckRequested": false, "suppliesAnswer": true,
    "providerStatus": "generated", "wordingSource": "qwen-generated",
    "targetAnchored": false, "rejectionReason": null
  }
}
```

Full responses also echo the synthetic scope, anonymous request/session IDs and
provider/bridge timing. `responseQuality` is fixed UNCLEAR on the demo endpoint;
lexical observations never map to a legacy success. The real legacy handler
retains its existing semantics, without a `teaching` field. No endpoint accepts
studentId, PIN, acceptedEvidence, completion, introSeen, audioAck or unlock claims.

### Identity, authorization and ownership

| Field/boundary | Harness behavior | Future production owner |
| --- | --- | --- |
| Service identity | Existing service-key verifier + mandatory configured key | Node/AI deployment owners |
| namespace/book/edition/track/lesson/activity/objective/version | Exact server-owned fixture grant, never trusted because client supplied it | Z.ai IDs/review provenance; Node curriculum authorization |
| Student identity/school/session | Not accepted; developer anonymous session only | Existing Node PIN/auth/session layer |
| revision/request ID | Bounded, locked in-memory development replay cache | Node durable idempotency, concurrency and persistence |
| correctness/independence/mastery/XP/unlocks | No acceptance or writes | Node deterministic evaluators and ProgressService |
| introductory video and speech ACK | No override fields; no application access | Existing Node gates before any authorized advancement |

Scope swaps fail before model calls; stale versions/revisions conflict. An exact
request replay returns the original response without inference or incrementing
revision. Reusing an ID with different content conflicts. A per-session lock
prevents duplicate concurrent inference. Sessions are limited to 64, 64 turns
each, with a 20-minute lifetime; restart loses them. This intentionally is not a
production database, distributed lock, progress store or resumption mechanism.
Only hashes, response candidates and bounded teaching context are retained;
raw transcripts are not placed in the replay cache or model prompts.

## Model and wording boundaries

The generator gets fixed synthetic facts, a strategy, language and a controlled
lexical signal. For an exact `on` response it may see the canonical fixture term
`on`; arbitrary child text, identity, PIN, history and audio are never forwarded.
No tool access or hidden provider substitution exists.

The local-only Qwen call has a four-second total deadline, including residency
check, HTTP, decoding and validation; no retries multiply it. Cold/unavailable
models use localized authored fallback. Model JSON requires exactly two strings,
bounded lengths, child-safe wording and fixture scope. English vocabulary checks,
privacy guards, target presence, obvious inverted relations and alternate-strategy
cues reject unsuitable candidates. They are **not** a semantic correctness proof.
Hindi/Marathi candidates may need linguistic/teacher review even when accepted.

If a native explanation has the fixture meaning but omits the English word, a
fixed `English: under.` anchor is added and `targetAnchored` explicitly reports
it. Independent checks never receive this anchor: answer-bearing messages are
rejected. Their question is always the reviewed synthetic check; generated
question text cannot reveal an answer through that channel. A generated
explanation/correction is still real model wording, not an authored selection.

Wrong, partial, silent and off-topic observations do not create accepted
evidence. STT failures/no mic skip inference and offer typing/waiting. Injection
attempts redirect without sending the attempted instructions to Qwen. Hinted or
repeated matches remain supported. An unhinted lexical match remains explicitly
UNVERIFIED_INDEPENDENT, not verified learning. The fixture has no retention rubric;
a RECALL request can request a check but cannot certify retention.
The harness also does not establish that a question is novel to the learner;
approved Node check selection must track prior examples and check provenance.

## Validation and limitations

See `RESULTS.md` and `evidence/` for actual runs, sample teacher text, cold/warm
latency and rejected-output counts. MockTransport fault tests are separate from
real Qwen measurements. No Azure call, raw child speech, classroom browser E2E,
concurrency capacity or human-reviewed teaching-quality result is claimed.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q tests
python -m compileall -q server dev_harness
```

## Separate gated Node integration plan — not implemented

1. PM reviews this versioned optional extension and failure semantics; Z.ai
   supplies approved dual-book identity mapping, rubrics and localized wording.
2. Verify the actual 8002 process, executable, working directory, revision and
   model/provider. An Ollama tag or this disposable server is not deployment parity.
3. In a separate approved Node PR, resolve authorized student/curriculum and all
   intro/video/audio-ACK gates server-side. Forward only minimized teaching signals
   under existing service authentication. No synthetic registry on student paths.
4. Node computes authoritative outcomes independently, owns accepted evidence and
   progress/XP/unlocks, and implements durable revision/idempotency and resume.
   Do not project lexical matches or generated praise into accepted mastery.
5. Copilot tests actual auth/grade/track isolation, classroom gate preservation,
   speech failures and retries; Antigravity owns UI display of advisory wording.
   Human review and latency budgets precede an explicit pilot release decision.
