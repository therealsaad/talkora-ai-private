"""Manual local-only synthetic benchmark. Never unloads or downloads a model.

Run from talkora-ai-starter: python -m tools.benchmark_teaching --output result.json
No service is started/reconfigured; absent 8002 is reported, never impersonated.
"""
import argparse
import asyncio
import json
import math
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from server.teaching import Card, Choice, Decision, Observation, QwenWordingSelector, Strategy


def summarize(samples):
    result = {}
    for state in ("cold", "warm", "unknown"):
        group = [s for s in samples if s["model_state_before"] == state]
        if not group:
            continue
        times = sorted(s["wall_seconds"] for s in group)
        result[state] = {"n": len(times), "p50_seconds": times[math.ceil(.5 * len(times)) - 1],
                         "p95_seconds": times[math.ceil(.95 * len(times)) - 1],
                         "valid_choices": sum(s["valid_choice"] for s in group)}
    return result


async def benchmark(samples, path="raw"):
    address = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    if address not in ("http://127.0.0.1:11434", "http://localhost:11434"):
        raise ValueError("Local Ollama only")
    captured = {}

    def capture(request):
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")}]})
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"wordingIndex":0}'}})

    card = Card(strategy=Strategy.CORRECT, language="en", supplies_answer=True,
                variants=("Good effort. Listen: cat.", "Let us try together: cat."),
                question="Which animal makes this sound?")
    decision = Decision(strategy=Strategy.CORRECT, observation=Observation.MISMATCH,
                        answer_support="UNKNOWN", language="en")
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as fake:
        await QwenWordingSelector(client=fake).select(grade=1, decision=decision, card=card)
    report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "model": captured["model"],
              "synthetic_only": True, "path": path, "request": captured, "samples": []}
    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
        try:
            response = await client.get("http://127.0.0.1:8002/health", timeout=2)
            report["service_8002"] = {"http_status": response.status_code,
                                      "note": "Not sufficient to prove source/provider parity"}
        except httpx.HTTPError as exc:
            report["service_8002"] = {"available": False, "error_type": type(exc).__name__}
        for index in range(samples):
            state, model_info = "unknown", {}
            try:
                status = await client.get(address + "/api/ps", timeout=3)
                status.raise_for_status()
                model_info = next((m for m in status.json()["models"] if m.get("name") == captured["model"]), {})
                state = "warm" if model_info else "cold"
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                pass
            sample = {"index": index, "model_state_before": state,
                      "size_vram": model_info.get("size_vram"), "valid_choice": False}
            started = time.monotonic()
            try:
                if path == "selector":
                    selected = await QwenWordingSelector(client=client).select(grade=1, decision=decision, card=card)
                    sample["valid_choice"] = selected is not None
                    sample["wall_seconds"] = round(time.monotonic() - started, 4)
                    report["samples"].append(sample)
                    print(json.dumps(sample), flush=True)
                    continue
                response = await client.post(address + "/api/chat", json=captured)
                response.raise_for_status()
                data = response.json()
                sample.update({key: data.get(key) for key in (
                    "load_duration", "prompt_eval_duration", "eval_duration", "total_duration",
                    "prompt_eval_count", "eval_count", "done_reason")})
                try:
                    choice = Choice.model_validate_json(data["message"]["content"])
                    sample["valid_choice"] = choice.wordingIndex < len(card.variants)
                except (ValueError, KeyError, TypeError):
                    pass
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                sample["error_type"] = type(exc).__name__
            sample["wall_seconds"] = round(time.monotonic() - started, 4)
            report["samples"].append(sample)
            print(json.dumps(sample), flush=True)
    report["summary"] = summarize(report["samples"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=6, choices=range(1, 21))
    parser.add_argument("--path", choices=("raw", "selector"), default="raw")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(benchmark(args.samples, args.path))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"]), flush=True)
