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
