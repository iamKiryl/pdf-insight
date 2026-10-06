"""Adapters from Cloudflare Worker ``env`` bindings to the runtime protocols.

The Python Workers SDK wraps ``env`` so plain dicts are converted to JS objects when passed to a
binding and results come back as Python objects (or JsProxy with ``to_py``). Nothing here imports
Pyodide, so this module is importable (and unit-tested) on regular CPython.
"""

from collections.abc import MutableMapping
from typing import Any

from .config import load_settings
from .runtime import AIProviderError, Runtime, classify_provider_error, provider_error_code


def _to_py(value: Any) -> Any:
    converter = getattr(value, "to_py", None)
    return converter() if callable(converter) else value


def _optional(env: Any, name: str) -> Any:
    try:
        return getattr(env, name)
    except (AttributeError, KeyError):
        return None


def env_var(env: Any, name: str) -> str | None:
    value = _optional(env, name)
    return value if isinstance(value, str) else None


class WorkersAIClient:
    def __init__(self, binding: Any) -> None:
        self._binding = binding

    async def run(self, model: str, inputs: dict[str, Any]) -> Any:
        try:
            result = await self._binding.run(model, inputs)
        except Exception as exc:  # JsException from the binding; message is classified, not logged
            text = str(exc)
            raise AIProviderError(
                classify_provider_error(text), provider_error_code(text)
            ) from None
        return _to_py(result)


class WorkersRateLimiter:
    def __init__(self, binding: Any) -> None:
        self._binding = binding

    async def allow(self, key: str) -> bool:
        outcome = _to_py(await self._binding.limit({"key": key}))
        if isinstance(outcome, dict):
            return bool(outcome.get("success"))
        return bool(getattr(outcome, "success", False))


def runtime_from_scope(scope: MutableMapping[str, Any]) -> Runtime:
    env = scope.get("env")
    settings = load_settings(lambda name: env_var(env, name))
    ai = _optional(env, "AI")
    ip_limiter = _optional(env, "ANALYZE_IP_LIMITER")
    global_limiter = _optional(env, "ANALYZE_GLOBAL_LIMITER")
    return Runtime(
        settings=settings,
        ai=WorkersAIClient(ai) if ai is not None else None,
        ip_limiter=WorkersRateLimiter(ip_limiter) if ip_limiter is not None else None,
        global_limiter=WorkersRateLimiter(global_limiter) if global_limiter is not None else None,
    )
