# SEC-001R: secrets out of claude_desktop_config.json, by a launcher that reads each repo's .env

**Repo:** seldon. Cross-repo by absolute path: `/Users/brock/Library/Application Support/Claude/claude_desktop_config.json`, the repos whose MCP servers it names. L4: commit and push in every repo touched. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01). Do not merge, do not touch the primary checkout.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8). **Re-issues:** SEC-001 (`1a2bb975`), refused at c13 because its premise used `$HOME`, which the premise runner does not expand (Issue `0fd2742a`). Supersedes seldon task fcc0ed89 (proposed 2026-09-20, never dispatchable: no headers).
**Governing:** squiddy R-11 (credentials live in `.env`, read through one accessor, never printed or moved by a task); operator statement 2026-09-20 (a secret inline in a config file is a violation).
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: a config rewrite, one launcher script, one test.
**Parts:** A 0.7, B 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: the config exists | check: `test -f "/Users/brock/Library/Application Support/Claude/claude_desktop_config.json"`
- premise: the config holds at least one inline secret-shaped value | check: `grep -qE '"(GITHUB_[A-Z_]*TOKEN|[A-Z_]*API_KEY|[A-Z_]*SECRET)"\s*:\s*"[^"]{8,}"' "/Users/brock/Library/Application Support/Claude/claude_desktop_config.json"`

Glob and read every sibling `*SEC-001R*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M.

## Part A

1. Read the config. For every server whose `env` block holds a value that looks like a secret (token, key, password), move the value into that server's repo `.env` (append if the key is absent; never print the value, never log it; the operator's existing `.env` files are the destination and `.env.example` gains the key name).
2. Replace the inline value with a launcher: `scripts/mcp_launch.sh <repo> <command...>` in seldon, which `set -a; . <repo>/.env; set +a` then execs the command. The config's `command` becomes the launcher; the `env` block keeps only non-secrets.
3. Rotation is not this task's job (it needs the GitHub web UI). Record in the RESULT that the moved values are the current ones.

Acceptance:
- `check: ! grep -E '"(GITHUB_[A-Z_]*TOKEN|[A-Z_]*API_KEY|[A-Z_]*SECRET)"\s*:\s*"[^"]{8,}"' "/Users/brock/Library/Application Support/Claude/claude_desktop_config.json"`

## Part B

1. Restart nothing. Write `docs/evidence/sec001/config_after.json` with values redacted, and a line per server naming the `.env` it now reads.
2. A test that the launcher exports the keys from a temp `.env` and execs its argument.

Acceptance:
- `check: pytest tests/test_sec001_launcher.py -q`

## Report

RESULT under 20 lines: servers changed, keys moved (names only), the redacted config path, and the note that Claude Desktop must be restarted once to pick up the launcher (an operator action only because the app is his; the task does not kill it).
