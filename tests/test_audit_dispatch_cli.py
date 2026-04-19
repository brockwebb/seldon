"""Integration tests for `seldon audit-dispatch` CLI."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.audit_dispatch import audit_dispatch_command


def test_cli_registered():
    """Smoke: command imports and has expected options."""
    runner = CliRunner()
    result = runner.invoke(audit_dispatch_command, ["--help"])
    assert result.exit_code == 0
    assert "--section" in result.output
    assert "--gate" in result.output


def test_fails_with_missing_section_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        audit_dispatch_command,
        ["--section", str(tmp_path / "nope.md"), "--gate", "content_audit"],
    )
    assert result.exit_code != 0


def test_fails_cleanly_when_litellm_missing_or_key_missing(tmp_path, monkeypatch):
    """If dispatch() raises RuntimeError, CLI should exit 2, not crash."""
    from seldon.commands import audit_dispatch as cmd_mod

    def fake_dispatch(**kwargs):
        raise RuntimeError("simulated: no API key")

    monkeypatch.setattr(cmd_mod, "dispatch", fake_dispatch)

    section = tmp_path / "section.md"
    section.write_text("# Test\n\nSome content.\n")

    runner = CliRunner()
    result = runner.invoke(
        audit_dispatch_command,
        ["--section", str(section), "--gate", "content_audit"],
    )
    assert result.exit_code == 2
