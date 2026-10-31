# Issue #15 evidence — 2026-10-31

## What passed

An isolated process started from this checkout on **127.0.0.1:18152**, using a
fresh random service key, returned HTTP 200 for the **existing**
`/v1/brain/respond` Class 1 word-repeat contract. The response contained the
existing fields, `activityComplete:false`, and no new `teaching` field. The
same disposable development app then accepted authenticated, fixture-authorized
synthetic teaching turns at `/dev/teaching/turn` and called real local Qwen.
The process was stopped after each run. No port 8002 process was started/stopped.

Source target reconciliation remains unchanged: Node's adapter expects
`/v1/brain/respond` (Class 1 default 8002); launch docs identify
`talkora-ai-starter/server.main:app`. The observed 8002 health probe failed
(ConnectTimeout), and no active Python teaching listener was observed. The
historical installed source differs from the repository. **This demonstration
proves the source contract on a separate port, not current deployment parity.**

## Real generated teaching examples

From the final synthetic English interaction:

1. Explain: “Under means below something. The ball is under the box, so it's
   below it.”
2. Synthetic response `on` → advisory CORRECT strategy. Qwen: “Under means below
   something. The ball is under the box.”
3. Repeated `on` → RETEACH. Qwen: “Think of the box as a little roof. The ball is
   below it — that's under.”
4. HINT → GUIDE; generated target explanation marks subsequent answers as
   supported. A response `under` requests an independent check, without accepting
   learning evidence. Repeating that answer again stays supported.
5. Independent check: “The toy is below the cup. Which position word fits?”
   A model message that gives away `under` is rejected; the reviewed no-answer
   prompt is used. An unhinted response in a fresh development session is merely
   UNVERIFIED_INDEPENDENT, with `validatedLearning:false`.

Hindi and Marathi scenarios include concept explanations, native-language
responses (`नीचे`, `खाली`), English wrong responses, alternate reteaching and
independent-check requests. Native meanings are supported observations, never
independent English proficiency. Some model explanations need a fixed English
target anchor; that transformation is explicitly reported. Accepted bilingual
wording still has awkward/tautological phrases and needs teacher/language review.
This is not a claim of classroom-quality pedagogy or a scored learning gain.

No teaching turn produces accepted evidence, mastery, completion, memory, XP,
unlocking or application writes. Node remains the only authority for those.

## Actual latency, not wording-selection benchmarks

Existing local model: `qwen3:4b-instruct`, on the same Windows 11 / i5-14450HX /
RTX 4050 Laptop machine used for PR #14. No model downloads, unloads, training,
cloud fallback or GPU configuration changes were performed.

Initial naturally cold run (historical initial harness revision):

- Cold-recovery HTTP response: approximately **172 ms**, localized fallback;
  the student-turn path did not load the model.
- Separate raw synthetic teaching-generation request: **4.219 s**, including
  **3.385 s model load**, 0.183 s prompt evaluation and 0.630 s generation
  (35 tokens). This measurement deliberately bypasses the four-second
  interactive deadline so loading can be observed. One model-cold sample is
  insufficient to estimate a cold p50/p95 distribution; filesystem cache was
  not flushed.
- The first run exposed scope/target validation failures; it is retained as
  historical evidence rather than represented as the final implementation.

Final varied warm run (21 sequential loopback turns):

| Turns | n | Generated wording accepted | HTTP client p50 | HTTP client p95 |
| --- | ---: | ---: | ---: | ---: |
| English | 9 | 7 | 937.151 ms | 1070.941 ms |
| Hindi | 6 | 4 | 2145.629 ms | 2794.841 ms |
| Marathi | 6 | 4 | 2103.937 ms | 2630.983 ms |
| All, including rejected-output fallback | 21 | 15 | 1881.056 ms | 2761.076 ms |

For **accepted generated** turns alone (n=15), HTTP p50 was 1709.097 ms and p95
2794.841 ms. Six Qwen candidates were rejected: two English independent messages
revealed the answer; four Hindi/Marathi reteaching candidates omitted the required
alternate-strategy cue. All six used truthful reviewed fallback, not a claim that
the generated output passed. No final-run model timeout was observed.

Provider-adapter time includes residency check, local HTTP, generation, parsing
and wording validation, not just GPU token generation. Handler bookkeeping above
that adapter had median **0.206 ms** for generated turns. Client time minus
provider-adapter time had median **4.066 ms** over all 21 turns (loopback,
authentication, FastAPI handling and serialization). These are small-sample,
single-client descriptive measurements, not capacity guarantees. Prompts vary by
strategy and language, with common prefixes benefiting from caching.

Raw evidence:

- `evidence/2026-10-31-cold-initial.json` — initial cold/recovery trace, including
  initial validation failures; predates the final anchor/scope/echo refinements.
- `evidence/2026-10-31-varied-final.json` — final 21-turn trace, full synthetic
  teacher text, explicit sources/rejection reasons and measured timings.

## Tests actually rerun

From `talkora-ai-starter`, using the isolated Python 3.12 environment:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
D:\talkora-ai-brain-v1\.venv\Scripts\python.exe -m pytest -q tests
D:\talkora-ai-brain-v1\.venv\Scripts\python.exe -m compileall -q server dev_harness
```

**188 passed, 1 skipped**, one existing Starlette/httpx TestClient deprecation
warning. The skip is the optional untracked experimental `/chat` seed.
Compilation also passed. Existing Class 1, poem, bilingual, KG compatibility,
hint-approval and service-security tests are included.

New tests cover opt-in/production/loopback/service-key denial, scope/track swaps,
stale versions/revisions, invalid lesson, identical replay, conflicting request ID,
concurrent duplicate serialization, full teaching sequence, supported/native/echo
answers, silence/STT/no mic, injection, privacy, rejection of asserted identity or
progress/gate overrides, malformed/unsafe/out-of-scope/inverted model wording,
alternate-strategy enforcement, independent answer leakage, bounded timeout,
missing/cold provider and successful generated JSON shape.

Model outage/timeouts/malformed responses are **MockTransport fault injection**,
not a real service shutdown. Real cold recovery and real warm generation are
measured separately. No working service was disturbed. No actual Azure, live
student audio, browser/classroom E2E, distributed persistence or load test is
claimed. No intro/audio-ACK gate is implemented or bypassed here; tests show the
harness cannot assert those fields and is absent from the production app. Actual
Node gate-preservation E2E belongs to the separate approved integration PR.

## Remaining review/release gates

- PM approval of the optional extension and stacked PR dependency.
- Z.ai/PM official dual-book/edition/track/objective identity agreement and human
  review of rubrics and bilingual teaching wording. No official records imported.
- Active 8002 deployment identity and full provider/service E2E verification.
- Separate Node-owned authentication, curriculum authorization, persistent replay,
  authoritative evaluation/evidence/progress and existing intro/speech gates.
- Classroom teaching quality evaluation. Lexical observations, a valid JSON reply
  and short latency do not establish validated learning.
