"""Tests for audit_dispatch model resolution and error handling."""
import os

import pytest

from seldon.paper.audit_dispatch import DEFAULT_MODEL, resolve_audit_model


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
