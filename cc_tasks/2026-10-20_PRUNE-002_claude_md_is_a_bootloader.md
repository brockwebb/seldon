# PRUNE-002: CLAUDE.md is a bootloader again; the command and tool lists are generated, not written; `seldon go` stops re-sending files the CLI already loaded

**Repo:** seldon (primary); squiddy by absolute path for Part C. L4: commit and push in both. Work on your worktree branch in seldon; commit squiddy on main by path through its hooks.
**Date:** 2026-10-20. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** operator doctrine "CLAUDE.md is a thin bootloader; the graph is the source of truth"; AD-038-R6 (a control ships with its negative control and a toil measure); the Composio rule the vendor survey recorded (an instruction that a mechanism enforces is documentation of the mechanism, never the enforcement). No new ruling; write the measurement as PRUNE-001's second weekly reading.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.25M tokens. Basis: the audit below is done; this is deletion, two generated sections, one measurement. The floor is 131K.
**Parts:** A 0.4, B 0.3, C 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: seldon's CLAUDE.md is over 20 KB | check: `python -c "import os,sys; sys.exit(0 if os.path.getsize('CLAUDE.md') > 20000 else 1)"`
- premise: go embeds the project CLAUDE.md | check: `grep -q "Project Context" seldon/commands/go.py`
- premise: the stale path is present | check: `grep -q "Documents/GitHub/seldon" CLAUDE.md`

Glob and read every sibling `*PRUNE-002*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M.

## The audit (2026-10-20, read-only, line numbers approximate)

seldon/CLAUDE.md, 24 KB: 60 percent narrates gates that `cc register`, `seldon verify`, `seldon handoff`, the dispatcher, the hooks and the MCP server already enforce with their own refusal text (skills table 25-58; MCP table 64-82 with a duplicate row and 12 tools missing; handoff rules 95-103; precedence 105-109; SEL-006 116-122; DESK-001 124-129; AD-038-R3 131-135; reconciler 137-141; prior-art log 143-145; governed graph 151-182; AD-035 286; init 291-295; ontology 299-315). 13 percent is stale (counts at 9-11; `/Users/brock/Documents/GitHub/...` at 233-234; a paper-foundations section for a repo with no `paper/`; an AD index that stops at AD-035 and skips 031 to 033 and 036 to 039). 17 percent duplicates `~/GitHub/CLAUDE.md` word for word (session protocol; paper reference syntax; key directories; five principles; docstring rule). 10 percent is needed: the identity line, the `.env`/dotenv pytest form (line 15), the pip install line, `SELDON_DEFAULT_PROJECT`, the cross-repo filing rule (111-114), the -ilities pointer. Trimmed, that is about 1.5 KB. One contradiction: the standards file says `seldon briefing`, this file and go.py say `seldon go`.

And every session receives the file up to three times: the CLI loads `~/GitHub/CLAUDE.md` and the project's, then `seldon go` embeds both again as "Engineering Standards" and "Project Context", plus its own role and command sections, which are themselves behind (no governed, models, dispatch, decision or prior-art commands).

## Part A: the cut

1. Rewrite `CLAUDE.md` to the needed lines only (the identity line and README pointer; line 15 as is; the pip line; `SELDON_DEFAULT_PROJECT`; the AD-036-R12 filing rule in two sentences; the -ilities pointer). Delete everything a mechanism enforces, everything stale, and everything the standards file already says. Retire the Success Contract paragraph (line 91): AD-037-R1's `check:`/`judgment:` marking superseded it. Target under 2 KB; record before and after bytes.
2. Fix the `briefing`/`go` contradiction in `~/GitHub/CLAUDE.md` §10 to `seldon go` (one word; that file is not in a repository, record its sha256 before and after in the evidence).

Acceptance:
- `check: python -c "import os,sys; sys.exit(0 if os.path.getsize('CLAUDE.md') < 2500 else 1)"`
- `check: ! grep -q "Documents/GitHub" CLAUDE.md`

## Part B: generated, not written

1. `seldon go`'s command section is generated from the click group at call time (every registered command and its one-line help), and its MCP section from `mcp_server.py`'s registered tools. Delete the hand-maintained `_AVAILABLE_COMMANDS_SECTION` text. A test asserts the printed list equals the registered set, so it cannot drift.
2. `seldon go` stops embedding `~/GitHub/CLAUDE.md` and the project `CLAUDE.md` when it runs inside Claude Code (`CLAUDECODE=1`), which already loaded both; it keeps them for a Desktop call where nothing else loads them. Record which path was taken in the go output's first line.
3. Toil measure: `seldon qc chart` reports, per week, the bytes of instruction context a launched session receives (both CLAUDE.md files plus the go output), from the launch records. First reading before and after this task.

Acceptance:
- `check: pytest tests/test_prune002_go_generated.py -q`
- `check: ! grep -q "_AVAILABLE_COMMANDS_SECTION = " seldon/commands/go.py`

## Part C: squiddy

1. Apply the same four-bucket classification to `/Users/brock/GitHub/squiddy/CLAUDE.md` (9.8 KB), with the mechanism named for every deleted line, in `docs/evidence/prune002/squiddy_audit.md`; cut it the same way; commit on squiddy main by path. Target under 3 KB; record before and after.

Acceptance:
- `check: python -c "import os,sys; sys.exit(0 if os.path.getsize('/Users/brock/GitHub/squiddy/CLAUDE.md') < 3500 else 1)"`
- `check: test -s docs/evidence/prune002/squiddy_audit.md`

## Report

RESULT under 15 lines: bytes before and after for both files; the generated sections' test; the go path rule; the first toil reading; tokens against 0.25M.
