import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdf_insight.app import create_app
from pdf_insight.config import load_settings
from pdf_insight.runtime import AIProviderError, Runtime

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
FIXTURES = CONTRACTS / "fixtures"
ORIGIN = "https://example.github.io"

POLISH_PAGE = (
    "Umowa ramowa nr 14/2026 zawarta w Warszawie w dniu 12 marca 2026 roku pomiędzy "
    "Nordwave Logistics sp. z o.o. a Kwadrat Software S.A. Przedmiotem umowy jest wdrożenie "
    "systemu. Wynagrodzenie za wdrożenie wynosi 184 500,00 PLN netto, tj. 226 935,00 PLN brutto. "
    "Abonament serwisowy wynosi 12 300 PLN netto miesięcznie."
)


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_model_output(**overrides: Any) -> dict[str, Any]:
    output: dict[str, Any] = {
        "insufficientContent": False,
        "language": "pl",
        "type": "umowa",
        "title": "Umowa ramowa nr 14/2026",
        "date": "2026-03-12",
        "summary": (
            "Umowa ramowa nr 14/2026 została zawarta 12 marca 2026 roku. Stronami są Nordwave "
            "Logistics sp. z o.o. oraz Kwadrat Software S.A. Wynagrodzenie za wdrożenie wynosi "
            "184 500 PLN netto."
        ),
        "keyPoints": [
            "Wdrożenie za 184 500 PLN netto.",
            "Abonament 12 300 PLN netto miesięcznie.",
            "Umowa zawarta 12 marca 2026 roku.",
        ],
        "organizations": ["Nordwave Logistics sp. z o.o.", "Kwadrat Software S.A."],
        "people": [],
        "amounts": [{"value": 184500, "currency": "PLN", "context": "Wdrożenie netto"}],
        "dates": [{"date": "2026-03-12", "context": "Zawarcie umowy"}],
        "keywords": ["umowa", "wdrożenie"],
    }
    output.update(overrides)
    return output


def make_request(pages: list[str] | None = None, file_name: str = "umowa.pdf") -> dict[str, Any]:
    texts = pages if pages is not None else [POLISH_PAGE, POLISH_PAGE]
    return {
        "fileName": file_name,
        "pageCount": len(texts),
        "pages": [{"page": i, "text": t} for i, t in enumerate(texts, start=1)],
        "pagesWithoutText": [
            i for i, t in enumerate(texts, start=1) if not any(c.isalpha() for c in t)
        ],
    }


class FakeAI:
    """Returns queued results (or raises queued exceptions) and records every call."""

    def __init__(self, *results: Any, delay: float = 0) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []
        self.delay = delay

    async def run(self, model: str, inputs: dict[str, Any]) -> Any:
        self.calls.append({"model": model, "inputs": inputs})
        if self.delay:
            import asyncio

            await asyncio.sleep(self.delay)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"response": result}


class FakeLimiter:
    def __init__(self, allow: bool = True, error: bool = False) -> None:
        self.allowed = allow
        self.error = error
        self.keys: list[str] = []

    async def allow(self, key: str) -> bool:
        self.keys.append(key)
        if self.error:
            raise RuntimeError("binding failure")
        return self.allowed


def make_client(
    ai: FakeAI | None,
    env: dict[str, str] | None = None,
    ip_limiter: FakeLimiter | None = None,
    global_limiter: FakeLimiter | None = None,
    limiters: bool = True,
) -> TestClient:
    values = {"ENVIRONMENT": "production", "ALLOWED_ORIGINS": ORIGIN, **(env or {})}
    settings = load_settings(values.get)
    ip = ip_limiter or (FakeLimiter() if limiters else None)
    glob = global_limiter or (FakeLimiter() if limiters else None)
    runtime = Runtime(settings=settings, ai=ai, ip_limiter=ip, global_limiter=glob)
    factory: Callable[[Any], Runtime] = lambda _scope: runtime  # noqa: E731
    return TestClient(create_app(factory))


@pytest.fixture
def provider_error() -> Callable[[str], AIProviderError]:
    return AIProviderError
