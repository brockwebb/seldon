"""A fixture model home for tests: a copy of the real registry and a lock naming a stub CLI.

No test reads the live lock in `models/` (it moves when Anthropic ships a model) and no test may
trigger a real `seldon models refresh` (four model calls): the registry copied here has both
`auto_on_*` switches off. `tests/conftest.py` points `SELDON_MODELS_HOME` at one of these for
every test; a test that needs its own (a stub CLI in its project) writes another.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from seldon import models as M

SELDON_REPO = Path(__file__).resolve().parents[1]
REAL_REGISTRY = SELDON_REPO / "models" / M.REGISTRY_FILE

#: The ids the fixture lock resolves. Equal to the 2026-10-09 heads, so the superseded ids the
#: tests plant (`claude-opus-5`, `claude-sonnet-5`) are stale against it exactly as in life.
FIXTURE_IDS = {"fable": "claude-fable-5-1", "opus": "claude-opus-5-5",
               "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
FIXTURE_CLI_VERSION = "9.9.9"


def write_models_home(root: Path, cli_path: str | Path = "/nonexistent/claude",
                      ids: dict | None = None, resolved_on: str = "2026-10-09") -> Path:
    """`<root>/models/` with the registry (auto refresh off) and a lock naming `cli_path`."""
    home = Path(root) / "models"
    home.mkdir(parents=True, exist_ok=True)
    reg = yaml.safe_load(REAL_REGISTRY.read_text(encoding="utf-8"))
    reg["refresh"]["auto_on_register"] = False
    reg["refresh"]["auto_on_dispatch"] = False
    (home / M.REGISTRY_FILE).write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")
    lock = {"schema": 1, "resolved_on": resolved_on, "resolved_at": f"{resolved_on}T00:00:00Z",
            "cli": {"version": FIXTURE_CLI_VERSION, "path": str(cli_path),
                    "npm_package": "@anthropic-ai/claude-code"},
            "families": {f: {"alias": f, "model": m} for f, m in (ids or FIXTURE_IDS).items()},
            "evidence": "docs/evidence/fixture.json"}
    (home / M.LOCK_FILE).write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    return home


#: The last line a shell stub CLI prints: a stream-json result whose served model is the
#: fixture's opus id, which is what a task with no `**Model:**` header (role `primary`) requests.
RECEIPT_LINE = ('{"type":"result","subtype":"success","usage":{"output_tokens":1},'
                '"modelUsage":{"claude-opus-5-5":{"outputTokens":1,"inputTokens":1}}}')


def shell_receipt(served: str = "claude-opus-5-5") -> str:
    """The shell line that prints a stream-json result naming `served`."""
    return "echo '" + RECEIPT_LINE.replace("claude-opus-5-5", served) + "'"


def use_stub_cli(tmp_path: Path, stub: Path) -> Path:
    """Point SELDON_MODELS_HOME at a fixture lock whose CLI is `stub`. conftest undoes it."""
    import os
    home = write_models_home(Path(tmp_path) / "models_home", cli_path=stub)
    os.environ["SELDON_MODELS_HOME"] = str(home)
    return home
