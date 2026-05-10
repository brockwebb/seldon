"""Audit dispatch via `claude --print` (Max OAuth) with LiteLLM fallback.

Default path routes a single audit prompt through the local `claude` CLI,
which uses the Max-subscription OAuth token. No API key required.

When `AUDIT_MODEL` is set to a non-default value (e.g. `gemini/gemini-2.5-flash`),
dispatch falls back to LiteLLM so dual-model SPOF-break audits keep working.
This preserves the AD-019 dual-model property without forcing an API key
for the default Claude path.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional


# "max" is the sentinel meaning "claude --print, no API key needed".
# Existing callers and tests import DEFAULT_MODEL — keep the constant.
DEFAULT_MODEL = "max"


def resolve_audit_model() -> str:
    """Return the audit model string. 'max' = claude --print (Max OAuth)."""
    return os.environ.get("AUDIT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def dispatch(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> str:
    """Dispatch a single prompt and return the model's response text.

    Default path: `claude --print --output-format json`, which uses Max
    OAuth. `temperature` and `max_tokens` are accepted for interface
    compatibility but not forwarded — claude --print does not expose them.

    Fallback path: if AUDIT_MODEL is set to a non-default value, route
    through LiteLLM with the requested provider/model.

    Raises:
        RuntimeError on missing CLI, timeout, non-zero exit, or LiteLLM
        failure. No silent fallback.
    """
    model = resolve_audit_model()
    if model != DEFAULT_MODEL:
        return _dispatch_litellm(prompt, system, temperature, max_tokens, model)
    return _dispatch_claude_cli(prompt, system)


def _dispatch_claude_cli(prompt: str, system: Optional[str]) -> str:
    """Invoke `claude --print --output-format json` and return the result text."""
    cmd = ["claude", "--print", "--output-format", "json"]
    if system:
        cmd.extend(["--append-system-prompt", system])
    cmd.append(prompt)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "claude CLI not found. Ensure Claude Code is installed and "
            "'claude' is on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("claude --print timed out after 300s") from exc

    if res.returncode != 0:
        raise RuntimeError(
            f"claude --print failed (exit {res.returncode}):\n"
            f"STDERR:\n{res.stderr[:2000]}"
        )

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return res.stdout.strip()
    return (data.get("result") or "").strip()


def _dispatch_litellm(
    prompt: str,
    system: Optional[str],
    temperature: float,
    max_tokens: int,
    model: str,
) -> str:
    """Fallback for non-default AUDIT_MODEL — preserves dual-model audits."""
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError(
            f"AUDIT_MODEL={model} requires litellm. "
            f"Run `pip install litellm>=1.50.0`."
        ) from exc

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
