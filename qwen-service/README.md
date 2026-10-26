# Talkora Miss Julie AI — local prototype

This is a **standalone prototype**, not a replacement for the existing Talkora backend. Curriculum entries are placeholders and MUST be reconciled with the canonical 110-level registry before integration. No student data is stored.

## Setup (PowerShell, from this folder)

```powershell
ollama list
ollama run qwen3:4b-instruct
# Exit Ollama chat with /bye
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tests/test_seed.py
uvicorn server.main:app --host 127.0.0.1 --port 8002 --reload
```

Keep Ollama running (normally as the desktop background service). In another PowerShell window:

```powershell
$body = @{ level_id = 'g00-l01'; message = 'Miss, hello kaise bolte hain?' } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8002/chat -Method Post -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Open http://127.0.0.1:8002/docs for Swagger UI.

## Limitations / next steps

- JSON output is syntactically checked but educational quality and safety require independent validation before use with children.
- Add per-session authenticated conversation history, guardrails, rate limiting, timeout/fallback, and privacy protections before connecting the live frontend.
- Do not expose this prototype endpoint publicly.
- Dataset for fine-tuning should be reviewed, licensed, de-identified and split by scenario into train/validation/test.
