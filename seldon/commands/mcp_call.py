"""`seldon mcp-call <tool>`: run one seldon-mcp tool in this process and print its answer (AD-038-R3).

Hidden: it is the child half of `seldon.mcp_server._runs_head`, not an operator command. The long-lived MCP server
spawns `<python> -P -m seldon mcp-call <tool>` for every mutating tool, writes the call's keyword arguments to stdin as
JSON, and relays the answer this prints. The child imports the repository's code as it stands now, so a merge under
`seldon/` never leaves the server answering from old code (`importlib.reload` cannot do this: names bound by
`from ... import` and existing instances keep the old objects; Python docs, `importlib.reload`).

The answer is the last stdout line, prefixed `RESULT_PREFIX` and JSON-encoded, so whatever a tool's body prints on
the way (click echoes, warnings) never corrupts it.
"""
from __future__ import annotations

import json
import os
import sys

import click

#: The prefix of the one line the parent reads. Anything before it is the tool's own chatter.
RESULT_PREFIX = "SELDON_MCP_RESULT "

#: Set in the child's environment: the tool body runs here, and a tool it calls never spawns again.
CHILD_ENV = "SELDON_MCP_CHILD"


@click.command("mcp-call", hidden=True)
@click.argument("tool")
def mcp_call_command(tool):
    """Run seldon-mcp tool TOOL with the JSON keyword arguments on stdin; print its answer."""
    os.environ[CHILD_ENV] = "1"
    from seldon import mcp_server

    fn = mcp_server.RAW_TOOLS.get(tool)
    if fn is None:
        raise click.ClickException(f"no seldon-mcp tool named {tool!r}")
    try:
        kwargs = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"the arguments on stdin are not JSON: {exc}")
    if not isinstance(kwargs, dict):
        raise click.ClickException("the arguments on stdin must be a JSON object")
    answer = fn(**kwargs)
    click.echo(RESULT_PREFIX + json.dumps(answer))
