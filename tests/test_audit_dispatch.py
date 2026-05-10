"""Tests for audit_dispatch model resolution and dispatch routing.

Default path uses `claude --print` (Max OAuth) — covered with subprocess.run
mocked. AUDIT_MODEL fallback uses LiteLLM — covered with litellm.completion
mocked. No live API calls.
"""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from seldon.paper import audit_dispatch
from seldon.paper.audit_dispatch import (
    DEFAULT_MODEL,
    dispatch,
    resolve_audit_model,
)


# ── resolve_audit_model ──────────────────────────────────────────────────────

def test_default_model_is_max():
    assert DEFAULT_MODEL == "max"


def test_resolve_default(monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    assert resolve_audit_model() == DEFAULT_MODEL


def test_resolve_env_override(monkeypatch):
    monkeypatch.setenv("AUDIT_MODEL", "gemini/gemini-2.5-flash")
    assert resolve_audit_model() == "gemini/gemini-2.5-flash"


def test_resolve_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AUDIT_MODEL", "   ")
    assert resolve_audit_model() == DEFAULT_MODEL


def test_resolve_strips_whitespace(monkeypatch):
    monkeypatch.setenv("AUDIT_MODEL", "  gemini/gemini-2.5-flash  ")
    assert resolve_audit_model() == "gemini/gemini-2.5-flash"


# ── claude --print path (default) ────────────────────────────────────────────

def _fake_subprocess_result(stdout: str, returncode: int = 0, stderr: str = ""):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@patch("subprocess.run")
def test_dispatch_default_uses_claude_cli(mock_run, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    mock_run.return_value = _fake_subprocess_result(
        json.dumps({"result": "findings: []\n"})
    )
    out = dispatch("audit this", system="you are an auditor")
    assert out == "findings: []"
    cmd = mock_run.call_args[0][0]
    assert cmd[:4] == ["claude", "--print", "--output-format", "json"]
    assert "--append-system-prompt" in cmd
    assert cmd[-1] == "audit this"


@patch("subprocess.run")
def test_dispatch_without_system_omits_append_system_prompt(mock_run, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    mock_run.return_value = _fake_subprocess_result(json.dumps({"result": "ok"}))
    dispatch("user only")
    cmd = mock_run.call_args[0][0]
    assert "--append-system-prompt" not in cmd
    assert cmd[-1] == "user only"


@patch("subprocess.run")
def test_dispatch_returns_raw_stdout_when_not_json(mock_run, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    mock_run.return_value = _fake_subprocess_result("plain text response\n")
    assert dispatch("x") == "plain text response"


@patch("subprocess.run")
def test_dispatch_raises_on_non_zero_exit(mock_run, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    mock_run.return_value = _fake_subprocess_result("", returncode=1, stderr="boom")
    with pytest.raises(RuntimeError) as excinfo:
        dispatch("x")
    msg = str(excinfo.value)
    assert "claude --print failed" in msg
    assert "boom" in msg


@patch("subprocess.run", side_effect=FileNotFoundError("no claude"))
def test_dispatch_raises_when_claude_missing(_mock, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="claude CLI not found"):
        dispatch("x")


@patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300))
def test_dispatch_raises_on_timeout(_mock, monkeypatch):
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="timed out"):
        dispatch("x")


# ── LiteLLM fallback (when AUDIT_MODEL is set) ───────────────────────────────

@patch("subprocess.run")
def test_dispatch_with_audit_model_skips_claude_cli(mock_run, monkeypatch):
    """When AUDIT_MODEL is set, subprocess.run must NOT be called."""
    monkeypatch.setenv("AUDIT_MODEL", "gemini/gemini-2.5-flash")
    with patch.object(audit_dispatch, "_dispatch_litellm", return_value="gemini said") as mock_lite:
        out = dispatch("p", system="s")
    assert out == "gemini said"
    assert mock_run.call_count == 0
    mock_lite.assert_called_once()


def test_dispatch_litellm_propagates_runtime_error(monkeypatch):
    monkeypatch.setenv("AUDIT_MODEL", "gemini/gemini-2.5-flash")

    class _FakeLiteLLM:
        @staticmethod
        def completion(**kwargs):
            raise RuntimeError("rate limited")

    with patch.dict("sys.modules", {"litellm": _FakeLiteLLM}):
        with pytest.raises(RuntimeError, match="Audit dispatch failed.*rate limited"):
            dispatch("p")


def test_dispatch_litellm_missing_package_error(monkeypatch):
    monkeypatch.setenv("AUDIT_MODEL", "gemini/gemini-2.5-flash")
    # Force ImportError by removing litellm from sys.modules and shadowing import
    import sys
    saved = sys.modules.pop("litellm", None)
    try:
        with patch.dict("sys.modules", {"litellm": None}):
            with pytest.raises(RuntimeError, match="requires litellm"):
                dispatch("p")
    finally:
        if saved is not None:
            sys.modules["litellm"] = saved
