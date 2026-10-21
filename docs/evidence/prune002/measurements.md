# PRUNE-002 measurements (2026-10-20)

## Part A

| File | Before (bytes) | After (bytes) |
|---|---|---|
| `seldon/CLAUDE.md` | 24,339 | 1,488 |
| `~/GitHub/CLAUDE.md` | 19,544 | 19,538 |

`~/GitHub/CLAUDE.md` is not in a repository. The only change is §10, start step 3: `seldon briefing` became
`seldon go`, which is what this repo's CLAUDE.md and `go.py` already said.

- sha256 before: `3f6d3491d264e5f9f9fc61294fcd7d33545851c40a818609c00c99a53f387416`
- sha256 after:  `85dc98ca6e005062285027d2ebeb6596429085a48e812f04619320760c25c536`

What stayed in `seldon/CLAUDE.md`: the identity line and README pointer (with the -ilities), the `.env`/dotenv
pytest line verbatim, the pip line, `SELDON_DEFAULT_PROJECT`, and the AD-036-R12 filing rule. Everything else went:
gate narration that the gate's own refusal text already carries, stale counts and paths, the paper sections (this
repo has no `paper/`), an AD index that stopped at AD-035, text copied from the standards file, and the Success
Contract paragraph (AD-037-R1's `check:`/`judgment:` marking superseded it).

## Part B: instruction context per launched session (first reading)

The measure (`seldon.core.instruction_context.measure`, recorded on every `dispatch_launched` from this task on,
charted per week by `seldon qc chart`) is the bytes of `~/GitHub/CLAUDE.md` + the project `CLAUDE.md` + `seldon go`'s
output on its Claude Code path. Both readings were taken in this worktree, against the same graph, on 2026-10-20.

| | standards | project CLAUDE.md | go output | total |
|---|---|---|---|---|
| before (go embeds both files) | 19,544 | 24,339 | 110,916 | 154,799 |
| after (go embeds neither inside Claude Code) | 19,538 | 1,488 | 79,321 | 100,347 |

The "before" go figure is derived from a measured run. `seldon go` at the pre-task code, run in this worktree,
printed 91,401 bytes. But `seldon.paths.resolve_system_standards` finds no standards file from a worktree, so that
run embedded the 29-byte "not found" notice in place of the 19,544-byte file. The primary checkout, where the
dispatcher runs, does resolve it, so 91,401 - 29 + 19,544 = 110,916. The "after" go figure was measured with
`scripts/prune002/reading.py ~/GitHub/CLAUDE.md`, which names the file explicitly.

Where the go bytes are now, by section, after the cut: handoff reconciliation ("One line") 24,558; agent roles
15,377; the generated commands and MCP tools 15,140 (108 commands, 32 tools; the hand-written list was 2,921 bytes with 22 command lines and 11 of the 32
tools); project state 13,087; dispatcher 4,332; role 3,291; workflows 2,636. They are
the next candidates for a cut.

## Part C

| File | Before (bytes) | After (bytes) |
|---|---|---|
| `squiddy/CLAUDE.md` | 10,068 | 2,145 |

Committed on squiddy main as `805e333` by path, through its hooks. Not pushed (this dispatched session may not
push). The audit is `squiddy_audit.md`.
