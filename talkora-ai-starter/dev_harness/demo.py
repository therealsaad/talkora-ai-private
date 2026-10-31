"""Reproducible real loopback/Qwen demo. Synthetic text only, no port 8002 changes.

python -m dev_harness.demo --port 18152 --output demo.json
The runner owns and stops only its newly created process. No model unloads.
"""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
from datetime import datetime, timezone

import httpx

from .coach import prompt, validate
from .fixtures import KEY


def percentile(values, quantile):
    return sorted(values)[math.ceil(len(values) * quantile) - 1] if values else None


async def run(port):
    if not 18000 <= port <= 18999:
        raise ValueError("Use an isolated development port")
    # Refuse an occupied port instead of accidentally benchmarking someone else's app.
    with socket.socket() as check:
        check.bind(("127.0.0.1", port))
    token = secrets.token_urlsafe(40)
    env = dict(os.environ, TALKORA_ENV="development", TALKORA_ENABLE_TEACHING_HARNESS="true",
               TALKORA_SERVICE_KEY=token, TALKORA_CLASS1_QWEN_PILOT="true")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen([sys.executable, "-m", "dev_harness", "--port", str(port)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "syntheticOnly": True, "port": port, "turns": []}
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(headers={"x-talkora-service-key": token}, timeout=12, trust_env=False) as client:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Disposable harness failed to start")
                try:
                    health = await client.get(base + "/health", timeout=.5)
                    if health.status_code == 200:
                        report["harnessHealth"] = health.json()
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.1)
            else:
                raise RuntimeError("Disposable harness startup deadline")
            legacy = await client.post(base + "/v1/brain/respond", json={
                "grade": 1, "levelId": "g01-l01", "studentMessage": "at",
                "currentQuestion": "Say the word at.", "activityTitle": "Listen and repeat"})
            legacy.raise_for_status()
            report["legacyContract"] = {"httpStatus": legacy.status_code, "response": legacy.json()}
            try:
                probe = await client.get("http://127.0.0.1:8002/health", timeout=1)
                report["existing8002"] = {"httpStatus": probe.status_code, "note": "No source parity established"}
            except httpx.HTTPError as exc:
                report["existing8002"] = {"available": False, "errorType": type(exc).__name__}

            scope = dict(zip(("namespace", "bookId", "edition", "trackId", "lessonId", "activityId", "objectiveId", "version"), KEY))
            async def call(event, text, language, sid, revision):
                request = {"contractVersion": "teaching.dev.v1", "sessionId": sid, "requestId": str(uuid4()),
                           "expectedRevision": revision, "scope": scope, "event": event,
                           "transcript": text, "language": language}
                started = time.perf_counter()
                response = await client.post(base + "/dev/teaching/turn", json=request)
                response.raise_for_status()
                result = response.json()
                row = {"scenario": event, "syntheticTranscript": text, "language": language,
                       "clientMs": round((time.perf_counter()-started)*1000, 3), "response": result}
                report["turns"].append(row)
                print(json.dumps({"scenario": event, "language": language, "clientMs": row["clientMs"],
                                  "providerStatus": result["teaching"]["providerStatus"],
                                  "reason": result["teaching"]["rejectionReason"]}), flush=True)
                return result["teaching"]["revision"]

            # Observe real cold recovery BEFORE any explicit benchmark warmup.
            await call("INTRODUCE", "", "en", str(uuid4()), 0)
            address = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
            if address not in ("http://127.0.0.1:11434", "http://localhost:11434"):
                raise ValueError("Benchmark uses existing local Ollama only")
            async with httpx.AsyncClient(timeout=90, trust_env=False) as local:
                ps = await local.get(address + "/api/ps")
                ps.raise_for_status()
                model = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
                cold = not any(m.get("name") == model for m in ps.json()["models"])
                started = time.perf_counter()
                raw = await local.post(address + "/api/chat", json=prompt("EXPLAIN", "en", "UNAVAILABLE"))
                raw.raise_for_status()
                data = raw.json()
                report["rawProviderMeasurement"] = {"model": model, "coldBefore": cold,
                    "wallMs": round((time.perf_counter()-started)*1000, 3),
                    **{key: data.get(key) for key in ("load_duration", "prompt_eval_duration", "eval_duration", "eval_count", "done_reason")}}
                try:
                    message, question = validate(data["message"]["content"], "EXPLAIN", "en")
                    report["rawProviderMeasurement"].update({"acceptedWording": True, "message": message, "question": question})
                except (ValueError, KeyError, TypeError):
                    report["rawProviderMeasurement"]["acceptedWording"] = False
                print(json.dumps(report["rawProviderMeasurement"]), flush=True)

            scenarios = {
                "en": [("INTRODUCE", ""), ("ANSWER", "on"), ("ANSWER", "on"), ("HINT", ""), ("ANSWER", "under"), ("ANSWER", "under")],
                "hi": [("INTRODUCE", ""), ("ANSWER", "नीचे"), ("ANSWER", "on"), ("ANSWER", "on"), ("ANSWER", "under")],
                "mr": [("INTRODUCE", ""), ("ANSWER", "खाली"), ("ANSWER", "on"), ("ANSWER", "on"), ("ANSWER", "under")],
            }
            for language, turns in scenarios.items():
                sid, revision = str(uuid4()), 0
                for event, transcript in turns:
                    revision = await call(event, transcript, language, sid, revision)
            # Additional varied warm samples for a less fragile small-sample p95.
            for language in ("en", "hi", "mr"):
                await call("EXPLAIN", "", language, str(uuid4()), 0)
            await call("ANSWER", "it is under", "en", str(uuid4()), 0)
            report["summary"] = {}
            for status in {r["response"]["teaching"]["providerStatus"] for r in report["turns"]}:
                rows = [r for r in report["turns"] if r["response"]["teaching"]["providerStatus"] == status]
                times = [r["clientMs"] for r in rows]
                report["summary"][status] = {"n": len(rows), "clientP50Ms": percentile(times, .5), "clientP95Ms": percentile(times, .95),
                    "providerP50Ms": percentile([r["response"]["teaching"]["latency"]["providerMs"] for r in rows], .5),
                    "bridgeOverheadP50Ms": percentile([r["response"]["teaching"]["latency"]["bridgeMs"] - r["response"]["teaching"]["latency"]["providerMs"] for r in rows], .5)}
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--port", type=int, default=18152)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.port))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"]), flush=True)
