"""Local CPU profile of the compact pipeline with a fake AI (no model calls, never deployed).

    uv run python tools/profile_compact.py ../.local/live/run2/request.json \
        ../.local/live/tuning/J-compact-v4-sample/response.json [--repeat 7] [--cprofile]

The model answer is rebuilt from a saved compact result: the candidate IDs whose contexts appear
in it plus its narrative fields, i.e. a valid selection the production parser accepts. Prints
CPU time (process_time) per stage for the first and the warm invocations, and the full request
through the FastAPI/ASGI app (TestClient, fake limiters, fake AI). Only numbers are printed —
no document text. Limits: CPython 3.13 on this machine, not Pyodide/workerd and not Cloudflare;
the AI binding, network wait and the timeout machinery are not exercised.
"""

import argparse
import asyncio
import cProfile
import io
import json
import pathlib
import pstats
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from conftest import ORIGIN, FakeAI, make_client
from pdf_insight.analyzer import _parse_payload
from pdf_insight.candidates import extract_candidates
from pdf_insight.compact import (
    OUTPUT_SCHEMA,
    assemble,
    build_messages,
    parse_selection,
)
from pdf_insight.config import load_settings
from pdf_insight.contract import AnalyzeRequest
from pdf_insight.models import build_inputs, profile_for


def selection_from_result(result: dict, candidates: list) -> dict:
    amount_ctx = {(a["value"], a["currency"], a["context"]) for a in result["amounts"]}
    date_ctx = {(d["date"], d["context"]) for d in result["dates"]}
    amount_ids = [c.id for c in candidates if c.kind == "amount"
                  and (float(c.value), c.currency, c.context) in amount_ctx]  # fmt: skip
    date_ids = [c.id for c in candidates if c.kind == "date" and (c.date, c.context) in date_ctx]
    main = next((c.id for c in candidates if c.kind == "date"
                 and c.date == result["document"]["date"] and c.id in date_ids), None)  # fmt: skip
    return {
        "insufficientContent": False, "language": result["document"]["language"],
        "type": result["document"]["type"], "title": result["document"]["title"],
        "mainDateId": main, "summary": result["summary"], "keyPoints": result["keyPoints"],
        "organizations": result["entities"]["organizations"],
        "people": result["entities"]["people"], "keywords": result["keywords"],
        "amountIds": amount_ids, "dateIds": date_ids,
    }  # fmt: skip


def cpu(fn):
    start = time.process_time_ns()
    value = fn()
    return value, (time.process_time_ns() - start) / 1e6


def stages(body: bytes, model_text: str, settings) -> dict[str, float]:
    times: dict[str, float] = {}
    data, times["json.loads(request)"] = cpu(lambda: json.loads(body))
    request, times["AnalyzeRequest.model_validate"] = cpu(
        lambda: AnalyzeRequest.model_validate(data)
    )
    candidates, times["extract_candidates"] = cpu(lambda: extract_candidates(request))
    messages, times["build_messages (mark document)"] = cpu(
        lambda: build_messages(request, candidates)
    )
    profile = profile_for(settings.ai_model)
    _, times["build_inputs (schema, params)"] = cpu(
        lambda: build_inputs(profile, messages, OUTPUT_SCHEMA, settings.ai_max_tokens)
    )
    payload, times["parse model JSON"] = cpu(lambda: _parse_payload({"response": model_text}))
    by_id = {c.id: c for c in candidates}
    selection, times["parse_selection (+ names, overview)"] = cpu(
        lambda: parse_selection(payload, by_id, request)
    )
    result, times["assemble (+ AnalysisResult validation)"] = cpu(
        lambda: assemble(request, selection)
    )
    _, times["serialize response"] = cpu(lambda: result.model_dump_json())
    return times  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("result")
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--cprofile", action="store_true")
    args = parser.parse_args()
    body = pathlib.Path(args.request).read_bytes()
    saved = json.loads(pathlib.Path(args.result).read_text(encoding="utf-8"))
    settings = load_settings({"AI_MODE": "compact"}.get)
    request = AnalyzeRequest.model_validate_json(body)
    selection = selection_from_result(saved, extract_candidates(request))
    model_text = json.dumps(selection, ensure_ascii=False)
    chosen = f"amounts={len(selection['amountIds'])} dates={len(selection['dateIds'])}"
    print(f"request bytes={len(body)} chars={request.total_chars} selected {chosen}")

    runs = [stages(body, model_text, settings) for _ in range(args.repeat)]
    print(f"\n{'stage (CPU ms, CPython)':42} {'first':>8} {'warm median':>12}")
    for name in runs[0]:
        warm = statistics.median(r[name] for r in runs[1:]) if len(runs) > 1 else runs[0][name]
        print(f"{name:42} {runs[0][name]:8.2f} {warm:12.2f}")
    totals = [sum(r.values()) for r in runs]
    print(f"{'sum of stages':42} {totals[0]:8.2f} {statistics.median(totals[1:]):12.2f}")

    client = make_client(FakeAI(*([selection] * (args.repeat + 1))), env={"AI_MODE": "compact"})
    full = []
    for _ in range(args.repeat):
        response, ms = cpu(lambda: client.post("/api/analyze", content=body, headers={
            "Origin": ORIGIN, "Content-Type": "application/json"}))  # fmt: skip
        assert response.status_code == 200, response.status_code
        full.append(ms)
    print(f"{'full POST via FastAPI/ASGI (TestClient)':42} {full[0]:8.2f} "
          f"{statistics.median(full[1:]):12.2f}")  # fmt: skip
    health = [cpu(lambda: client.get("/api/health"))[1] for _ in range(args.repeat)]
    print(f"{'GET /api/health via TestClient':42} {health[0]:8.2f} "
          f"{statistics.median(health[1:]):12.2f}")  # fmt: skip

    if args.cprofile:
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(5):
            stages(body, model_text, settings)
        profiler.disable()
        out = io.StringIO()
        pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(25)
        text = out.getvalue()
        print("\n".join(line[:150] for line in text.splitlines()[:60]))
    asyncio.get_event_loop_policy()  # keep asyncio imported for TestClient threads
    return 0


if __name__ == "__main__":
    sys.exit(main())
