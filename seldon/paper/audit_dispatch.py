"""Dual-model audit dispatch via LiteLLM (AD-019 SPOF break).

Reads AUDIT_MODEL env var and routes a single prompt through the configured
provider. Returns raw response text. Caller is responsible for parsing.
"""
from __future__ import annotations

import os
from typing import Optional


DEFAULT_MODEL = "anthropic/claude-3-5-sonnet-latest"


def resolve_audit_model() -> str:
    """Return the model string to use for the current audit run."""
    return os.environ.get("AUDIT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def dispatch(prompt: str, system: Optional[str] = None,
             temperature: float = 0.2, max_tokens: int = 4096) -> str:
    """Dispatch a single prompt via LiteLLM. Returns response text.

    Raises RuntimeError if the API key for the resolved model is missing
    or if the call fails. No silent fallback.
    """
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError(
            "litellm not installed. Run `pip install litellm>=1.50.0`."
        ) from exc

    model = resolve_audit_model()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise RuntimeError(f"Audit dispatch failed for model {model}: {exc}") from exc

    return response.choices[0].message.content or ""
