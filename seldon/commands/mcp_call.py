"""`seldon mcp-call <tool>`: run one seldon-mcp tool in this process and print its answer (AD-038-R3).

Hidden: it is the child half of `seldon.mcp_server._runs_head`, not an operator command. The long-lived MCP server
spawns `<python> -P -m seldon mcp-call <tool>` for every tool, reads included since MCP-001, writes the call's keyword
arguments to stdin as JSON, and relays the answer this prints. The child imports the repository's code as it stands
now, so a merge under `seldon/` never leaves the server answering from old code (`importlib.reload` cannot do this:
names bound by `from ... import` and existing instances keep the old objects; Python docs, `importlib.reload`).

The answer is the last stdout line, prefixed `RESULT_PREFIX` and JSON-encoded, so whatever a tool's body prints on
the way (click echoes, warnings) never corrupts it. A string answer ends with `code_line()`, the checkout the child
imported: SEL-006's record of what a process loaded, kept as a note instead of a refusal (MCP-001), so a transcript
shows which code answered.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import click

#: The prefix of the one line the parent reads. Anything before it is the tool's own chatter.
RESULT_PREFIX = "SELDON_MCP_RESULT "

#: Set in the child's environment: the tool body runs here, and a tool it calls never spawns again.
CHILD_ENV = "SELDON_MCP_CHILD"

#: How many hex digits of the HEAD sha the note carries: git's own `--short` default.
SHA_DIGITS = 7


def code_line(repo: Path) -> str:
    """`code: <sha>` for the checkout at `repo`, naming uncommitted edits under its `seldon/` when there are any.

    Never raises: a directory git cannot read (an installed, non-editable package) is named as such."""
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", f"--short={SHA_DIGITS}", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode != 0:
        return f"code: unknown ({repo} is not a git checkout)"
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "seldon"],
                           capture_output=True, text=True).stdout.strip()
    return f"code: {head.stdout.strip()}" + (" + uncommitted changes under seldon/" if dirty else "")


#: What separates a tool's own answer from its `code_line()`.
CODE_LINE_SEPARATOR = "\n\n"


def without_code_line(answer: str) -> str:
    """`answer` with the trailing `code_line()` removed: the tool's own words, for a comparison with the CLI's."""
    body, sep, tail = answer.rpartition(CODE_LINE_SEPARATOR)
    return body if sep and tail.startswith("code: ") and "\n" not in tail else answer


def stale_schema_note(tool: str, fn, kwargs: dict) -> str | None:
    """SEL-052 (factory's 2026-11-26 filing, item 3): the parameters this checkout's tool takes that the server did
    not send, said in the answer, or None.

    The child runs the checkout's code, but the SCHEMA a client sees is the one the long-lived server registered when
    it started (`_runs_head` binds every argument of the signature it started with, defaults included). So a
    parameter added since the server started is one the client cannot pass: factory's Desktop called
    `seldon_go(portfolio=true)` on 2026-11-26 and was answered as if it had not, with nothing saying why."""
    import inspect
    have = [n for n, p in inspect.signature(fn).parameters.items()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    missing = [n for n in have if n not in kwargs]
    if not missing:
        return None
    return (f"note: this seldon-mcp server was started on older code. `{tool}` here takes "
            f"{', '.join(missing)}, which the schema it serves lacks, so a client cannot pass "
            f"{'it' if len(missing) == 1 else 'them'} and the default answered. Restart the seldon-mcp server "
            f"(quit and reopen Claude Desktop) to serve the current schema (SEL-052).")


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
    if isinstance(answer, str):
        note = stale_schema_note(tool, fn, kwargs)
        if note:
            answer = f"{answer}{CODE_LINE_SEPARATOR}{note}"
        answer = f"{answer}{CODE_LINE_SEPARATOR}{code_line(Path(mcp_server.__file__).resolve().parent.parent)}"
    click.echo(RESULT_PREFIX + json.dumps(answer))
