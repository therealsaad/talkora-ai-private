# Class 1 Balbharati-aligned adaptive Qwen pilot

Scope: **canonical `g01-l01` only**. This is Talkora-created companion practice
aligned to **English Balbharati Standard One, Unit One, 1.1 My First Day**
(page 1), plus the existing eight foundation words (`am, an, at, in, is, it,
on, up`). It does **not** duplicate the publisher's poem or artwork.

## What changes

- Existing `/v1/brain/respond` request/response field names remain unchanged.
- `hintLevel`, `waitingForRetry`, and `recentMistakes` (already provided by the
  bridge) choose one of `MODEL`, `GUIDE`, `PRACTISE`, and `EXTEND`.
- This is **learning support**, not IQ assessment or a verified mastery score.
- Qwen supplies only a short supplementary coaching hint. Node remains the
  sole authority for actual progress, completion and student memory.
- When a word-repeat activity is already handled by the fixed response guard,
  **no Ollama call occurs**. This removes a needless model round-trip.
- For open school conversations Qwen sees only the active teacher prompt,
  student transcript, approved local unit context, and teaching mode.
- If local Ollama is temporarily unavailable, the deterministic coaching
  response still works. This fallback never changes student progress.
- KG, Class 4, and every other grade/level remain unchanged.

## Run tests (the Qwen service virtual environment)

```powershell
cd "D:\allabouttalkora\live_talkora\talkora1\talkora\ai-models\talkora-ai-starter"
python -m pytest -q tests/test_class1_compat.py tests/test_class1_response_guard.py tests/test_class1_adaptive.py tests/test_class1_adaptive_data.py
```

## Prepare new reviewable training examples (no GPU needed)

```powershell
python -m training.class1_adaptive_data
```

Generates **240 synthetic examples** with target-word-held-out validation and
test splits (192/24/24), across English/Hindi/Marathi support and four teaching
modes. This **does not train the running model**. Manually review the generated
text, educational correctness, spelling, bilingual content, curriculum and
copyright alignment before any GPU training.

## Optional later research training (separate environment)

Existing `training/class1_pilot.py` has an experimental low-VRAM QLoRA path:

```powershell
python -m training.class1_pilot train --data-dir .\datasets\training\class1-adaptive
```

Only do this **after human approval** and in the separate CUDA training venv.
That script's default base is `Qwen/Qwen3-1.7B`, **not** the running Ollama
`qwen3:4b-instruct`: an adapter trained on 1.7B cannot be directly applied to
the 4B model. Fine-tuning, evaluation against blind teacher-reviewed cases,
and model deployment are separate future steps. Do not claim the live 4B is
fine-tuned.

## Acceptance checks

1. Repeat `Say at` with `at` and `on`: confirm feedback is fast, safe, and
   `responseQuality` / `shouldRetry` retain their current meanings.
2. School-talk prompt: ensure the AI discusses school, not other chapters.
3. Check Hindi/Marathi support for difficult attempts.
4. Check unavailable Ollama and slow response handling; repeat activities
   must still work. A cold guided reply may still take up to 12 seconds.
5. Check the authenticated student browser session, STT, S3 Priya audio,
   homework, and MongoDB progress end to end before publishing the draft.

Do not upload raw child speech or personally identifying information into the
training set. The teaching engine must not infer IQ from response times.
