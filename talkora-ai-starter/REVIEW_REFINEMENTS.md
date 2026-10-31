# PR #14 review refinements — 2026-10-31

Addresses [the PM review](https://github.com/therealsaad/talkora-ai-private/pull/14#issuecomment-6542070305).
No HTTP activation, deployment, app changes or model replacement.

## Real Qwen measurements

Machine: Windows 11, Python 3.12.10, Intel Core i5-14450HX, NVIDIA GeForce RTX
4050 Laptop GPU. Local Ollama reports `qwen3:4b-instruct` (4.0B, Q4_K_M,
4096 context, llamacpp runner); `/api/ps` reports
3,180,247,121 VRAM bytes for the warm model. No model was downloaded or unloaded.
The first model residency check was naturally empty, permitting a true model-cold
sample without disrupting another process. This is model-cold, not a reboot or
guaranteed cold filesystem cache.

| Measurement | n | p50 | p95 | Valid index responses |
| --- | ---: | ---: | ---: | ---: |
| Original selector payload, naturally cold model | 1 | — | — | 1/1 |
| Original payload, warm direct Ollama | 5 | 0.157 s | 0.172 s | 5/5 |
| Revised warm-only selector, including residency check | 20 | 0.171 s | 0.172 s | 20/20 |

The single cold sample took **9.703 s**. Ollama reported **9.405 s loading**,
0.139 s prompt evaluation and 0.146 s generation. There are insufficient cold
samples to estimate a cold latency distribution; raw nearest-rank single-sample
statistics in the JSON are not population percentiles. The six-second initial
failure is consistent with model loading, not six seconds of variant reasoning.

Samples were sequential with the same synthetic English two-variant prompt,
temperature 0, num_predict 24 (eight tokens generated in the baseline). Warm
requests benefit from prompt/KV caching. They do not establish latency for full
Class 1 poem coaching, varied prompts, concurrency, Hindi/Marathi generation or
classroom teaching quality. A valid index is syntax/selection evidence only.

Raw samples, request and metadata:

- `benchmarks/teaching-2026-10-31-baseline.json`
- `benchmarks/teaching-2026-10-31-selector.json`

Reproduce from `talkora-ai-starter`:

```powershell
..\.venv\Scripts\python.exe -m tools.benchmark_teaching --path raw --samples 6 --output raw.json
..\.venv\Scripts\python.exe -m tools.benchmark_teaching --path selector --samples 20 --output selector.json
```

The manual raw path intentionally allows up to 120 seconds to measure loading;
it bypasses the student-turn deadline. It uses synthetic text only and never
starts, reconfigures or impersonates the 8002 service. It never forces a cold
state; if the model is already resident, all samples are labeled warm.

**Decision:** no cold loading on an optional wording-selection turn. The module
checks residency, defaults to a one-second total budget (maximum two seconds),
and immediately uses authored wording if cold/unknown. Retry and preflight share
the budget. Repeated difficulties already choose deterministic alternate wording;
single-variant cards now skip inference too. A race between residency check and
eviction can still hit the deadline; cancellation cannot guarantee Ollama stops
all upstream work. No automatic warming or background session is introduced.

Keep this optional selector disabled by default. Even ~170 ms is overhead for
choosing authored variants with no demonstrated pedagogical benefit. The reviewed
deterministic strategy/wording path remains sufficient. Any later interactive use
needs evidence of teaching benefit and a service-level latency budget.

## School vocabulary and privacy

Removed blanket keyword rejection of `your name`, `address`, `phone`, etc. An
approved explanation of those words is not a request for a real child's data.
Tests permit metalinguistic phrases and exact quoted-word practice, including
"Say the words 'your name'". Direct requests such as "Say your name", "What is
your school name", real address/phone/password requests, and tested Hindi/Marathi
equivalents remain blocked.

`fictional_names=True` is an explicit, trusted authored-card setting, not client
input. It narrowly permits "Ask a fictional puppet, 'What is your name?'". It
does not permit real names, addresses or credentials; additional solicitation
in the same card is still rejected. It is not an approval flag or a comprehensive
multilingual safety classifier. Curriculum/educator review is still mandatory.
No private child data enters Qwen prompts.

## Lexical matching is not validated learning

Removed the internal `legacy_response()` serializer rather than claiming a
legacy consumer cannot interpret ADEQUATE as success. The Node adapter preserves
responseQuality, so introducing that mapping would be an avoidable integration
risk even though the module is not currently connected to HTTP.

The research-only `advisory_response()` uses explicit LEXICAL_MATCH,
LEXICAL_OVERLAP and LEXICAL_MISMATCH labels and **always** sets
`validatedLearning: false`. It has no responseQuality, evaluation, accepted skills,
completion, XP or unlock fields. Echo/hinted answers remain SUPPORTED;
UNVERIFIED_INDEPENDENT is not validated independence or retention. No grade of
semantic correctness, comprehension or pronunciation is inferred from word
matching. Node alone evaluates and accepts learning evidence.

Tests prove the serializer is absent, exact matches never assert validated
learning, and no new route/field is installed. Existing Class 1, KG, multilingual,
poem, hint approval and bridge-auth tests remain the compatibility checks.

## Book/edition/track isolation — proposed adapter, not an agreed dataset schema

Read Z.ai's handoff and checkpoint in `talkor/curriculum-research/` without editing
them. They distinguish syllabus verification from pedagogy approval, report two
Class 1 English textbook tracks, and explicitly request PM decisions on identity
and book policy. The material is not human-approved runtime curriculum.

The internal `CurriculumRef` now requires namespace, book_id, edition and track_id.
Registry keys also include lesson, activity, objective and version. Tests isolate
two synthetic tracks/books and a second edition with identical local objective
IDs: authorization cannot cross those namespaces. A non-synthetic record with
PENDING review status is rejected. No official IDs, schemas or chapters are
invented/imported; there is no production registry or HTTP consumer.

**Still pending:** Z.ai/PM agreement on canonical book/edition/track IDs, published
objective mappings, review provenance and human-approved rubrics/scaffolds. A
caller-populated APPROVED value/reference is not proof of genuine review; the
future trusted import path must verify provenance. This code establishes internal
isolation and fail-closed defaults, not organizational approval.

## Deployment and fault-injection evidence

Port 8002 had no listener; process inventory showed Ollama and IDE language
servers but no active Python teaching service. The benchmark's HTTP health probe
also reports ConnectError. Therefore **actual 8002 p50/p95, effective running
Python revision/provider and deployment parity remain unverified**. No working
service was stopped, overwritten or started in its place. The installed historical
starter `server/main.py` hash differs from this repository. Launch docs and Node
adapters establish the expected target, not a live deployment identity.

Offline fault injection uses httpx.MockTransport: absent/cold/wrong model,
residency-check timeout, connection failure, 4xx/5xx, bounded retry, malformed JSON,
unexpected keys, oversized output, cancellation, speech unavailable and injection.
These are mocked faults, not a stopped real model/service experiment. The revised
warm-only path was exercised against real Ollama; actual cold-skip behavior is
covered offline, since the benchmark leaves the loaded model untouched.

No `server/main.py`, `compat.py`, `class1*.py`, `phase3/`, KG route, Priya, Node,
frontend or curriculum files are modified. Existing Class 1 fail-closed model
behavior remains intact. No Azure or full application E2E result is claimed.

## Verification

Latest full starter-suite run: **147 passed, 1 skipped**, with one existing
Starlette/httpx TestClient deprecation warning. The skip is the optional untracked
experimental chat seed. Exact command:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
..\.venv\Scripts\python.exe -m pytest -q tests
```

Review status: isolated refinements ready for review. Runtime activation, dataset
agreement, deployment parity and classroom quality approval remain release gates.
