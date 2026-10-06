"""LOCAL-ONLY profiling Worker (never deployed; no AI binding): runs compact pipeline stages N
times inside one request so the client can time them in workerd/Pyodide.

    uv run pywrangler dev --config wrangler.profile.jsonc --port 8790
    POST /?stage=<noop|validate|extract|pipeline>&n=<1..50>
    body: {"request": ..., "selection": ...}

Only timings leave the Worker; nothing is logged. Copy the package first (symlinks are not
bundled): rm -rf tools/workerd_profile/pdf_insight && cp -R src/pdf_insight tools/workerd_profile/
"""

import json

from workers import Response, WorkerEntrypoint

from pdf_insight.candidates import extract_candidates
from pdf_insight.compact import assemble, build_messages, parse_selection
from pdf_insight.contract import AnalyzeRequest


def _pipeline(raw: dict, selection: dict) -> int:
    request = AnalyzeRequest.model_validate(raw)
    candidates = extract_candidates(request)
    build_messages(request, candidates)
    chosen = parse_selection(selection, {c.id: c for c in candidates}, request)
    return len(assemble(request, chosen).model_dump_json())


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        params = dict(p.split("=", 1) for p in request.url.split("?", 1)[-1].split("&") if "=" in p)
        stage, n = params.get("stage", "noop"), max(1, min(50, int(params.get("n", "1"))))
        data = json.loads(await request.text())
        raw, selection = data["request"], data["selection"]
        size = 0
        for _ in range(n):
            if stage == "validate":
                size = AnalyzeRequest.model_validate(raw).total_chars
            elif stage == "extract":
                size = len(extract_candidates(AnalyzeRequest.model_validate(raw)))
            elif stage == "pipeline":
                size = _pipeline(raw, selection)
        return Response(json.dumps({"stage": stage, "n": n, "size": size}),
                        headers={"content-type": "application/json"})  # fmt: skip
