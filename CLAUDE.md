# Seldon — Research Operating System

The graph is the mind. The agents are the hands. Vision and the guaranteed properties (-ilities): `README.md`.

Orient with `seldon go`; it lists every command and MCP tool from the code. Every gate (`cc register`, `verify`,
`handoff`, the dispatcher, the hooks) states its own rule when it refuses; this file does not repeat them.

## Environment

**Neo4j credentials are in `.env`.** CC: you have the password. Load it with `dotenv` or read `.env` directly. Do NOT skip Neo4j-dependent tests. Do NOT ask for the password. Run the suite via python-dotenv: `python -m dotenv -f .env run -- python -m pytest tests/ -v`. Do NOT use `source .env && pytest` — line 4 of `.env` does not `source` cleanly in zsh, so that form silently skips every DB test (recorded in `cc_tasks/2026-09-02_snapshot_artifacts_verify_RESULT.md`). Passing `NEO4J_PASSWORD` explicitly also works.

**Python:** Seldon is pip-installed in the active environment; `seldon` is on PATH.

**MCP default project:** `SELDON_DEFAULT_PROJECT=/path/to/project` in the `seldon-mcp` env block of
`claude_desktop_config.json`; `seldon_go` without `project_dir` falls back to it.

**Filing into another repository (AD-036-R12).** Register a task file written into another repository's `cc_tasks/`
in the same step: `seldon cc register --project <that repo> --allow-untracked <file>`, which commits it. An
unregistered filing dirties that tree, and its dispatcher then refuses every task.
