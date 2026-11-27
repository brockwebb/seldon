"""SEL-052 Part B: factory's 2026-11-26 filing item 3, "the MCP portfolio brief returned one project".

`seldon_go(project_dir, brief, portfolio)` is the checkout's tool, but Desktop's client was served the schema the
long-lived server registered at its start, `(project_dir, brief)`: the call's `portfolio=true` never reached the child,
which answered the default. The child now says so, naming the parameters and the remedy (restart the server).
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from seldon import mcp_server as M
from seldon.commands import mcp_call as MC


def _tool(project_dir: str = ".", brief: bool = False, portfolio: bool = False) -> str:
    return f"portfolio={portfolio}"


def test_a_parameter_the_server_did_not_send_is_named():
    note = MC.stale_schema_note("seldon_go", _tool, {"project_dir": ".", "brief": True})
    assert note and "takes portfolio" in note and "Restart the seldon-mcp server" in note
    assert MC.stale_schema_note("seldon_go", _tool, {"project_dir": ".", "brief": True, "portfolio": False}) is None


def test_the_child_appends_the_note_before_its_code_line(monkeypatch):
    monkeypatch.setitem(M.RAW_TOOLS, "seldon_fake_go", _tool)
    res = CliRunner().invoke(MC.mcp_call_command, ["seldon_fake_go"],
                             input=json.dumps({"project_dir": ".", "brief": True}))
    assert res.exit_code == 0, res.output
    line = [x for x in res.output.splitlines() if x.startswith(MC.RESULT_PREFIX)][-1]
    answer = json.loads(line[len(MC.RESULT_PREFIX):])
    body = MC.without_code_line(answer)
    assert body.startswith("portfolio=False") and "takes portfolio" in body
    # A server whose schema matches adds nothing.
    res = CliRunner().invoke(MC.mcp_call_command, ["seldon_fake_go"],
                             input=json.dumps({"project_dir": ".", "brief": True, "portfolio": True}))
    answer = json.loads([x for x in res.output.splitlines() if x.startswith(MC.RESULT_PREFIX)][-1]
                        [len(MC.RESULT_PREFIX):])
    assert MC.without_code_line(answer) == "portfolio=True"
