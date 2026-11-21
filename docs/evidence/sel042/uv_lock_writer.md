# SEL-042 ADDENDUM 01: what wrote `uv.lock` into seldon's primary checkout, and how long the alarm stood

Read on 2026-11-21 by SEL-042's session. Read only: nothing in seldon's primary, hazbrief-mcp or the transcripts was
changed. Scripts: `/tmp/sel042/uv_hunt.py`, `/tmp/sel042/uv_record.py`, `/tmp/sel042/alarm.py` (their findings are
quoted below).

## The file

`/Users/brock/GitHub/seldon/.seldon/quarantine_uv.lock_2026-11-21` (moved there by Desktop, unchanged): 262,297
bytes, mtime 2026-11-20 18:01 EST (23:01:38Z). `version = 1`, `revision = 3`, `requires-python = ">=3.10"` (seldon's
`pyproject.toml`), 52 packages, and the project itself as `name = "seldon"`, `source = { editable = "." }` with
seldon's six dependencies (click, mcp, neo4j, pydantic, python-dotenv, pyyaml). So `uv` ran with seldon's checkout as
its project. The same command made `/Users/brock/GitHub/seldon/.venv/` (mtime 18:01 EST), which `.gitignore` line 204
ignores, so only `uv.lock` was dirt. `.venv/` is still there.

## The writer

Claude Code transcript `~/.claude/projects/-Users-brock-GitHub-hazbrief-mcp--claude-worktrees-wiggly-giggling-pine/a829d9a0-121b-44bf-b842-fa102c365645.jsonl`:
the OODA knowledge source seldon's dispatcher launched in hazbrief-mcp (AD-038-R16; its prompt begins "OODA
(AD-038-R16, ...) on completed task f44dd32b cc_tasks/2026-11-20_HB-212_benchmark_status_by_significance.md"), in
worktree `wiggly-giggling-pine`.

- 23:01:33Z it wrote `cc_tasks/2026-11-20_HB-213_public_package_build_ADDENDUM_02_hb212_missed_census_wording_carry_it_here.md`
  in its worktree.
- 23:01:36.696Z it ran, to check that addendum against AD-038-R24:
  `cd ../../../../seldon && uv run --quiet python -c "import sys;from seldon.core.dispatch import addendum_header_refusal as r ..." <addendum path>`
- 23:01:40.499Z the tool returned `None` (the addendum passed). The file's mtime, 23:01:38Z, falls between.

`../../../../seldon` from `hazbrief-mcp/.claude/worktrees/wiggly-giggling-pine` is seldon's primary checkout. `uv run`
there locked and synced seldon as a uv project.

## Should the file exist?

No. seldon is installed with pip, editable, from its primary checkout, and has never carried a `uv.lock` (no commit
on main touches the path). The writer is the defect: seldon's dispatcher launched a session whose prompt forbade
commits, pushes and writing `seldon` commands but did not forbid running another repository's package manager. AD-038-R31
states the boundary in the OODA prompt (`seldon/core/ooda.py`, `tests/test_sel042_ooda_boundary.py`). The return to
hazbrief-mcp reports it, since the session ran under hazbrief's dispatcher.

The quarantined copy and the stray `.venv/` are in seldon's primary checkout, outside this task's worktree; the
RESULT gives the operator the lines to remove both.

## How long the alarm stood, and where it was shown (for SEL-044)

From `logs/seldon_dispatch.log` and seldon's event store:

| when (UTC) | what |
|---|---|
| 2026-11-20 23:01:38 | `uv.lock` written |
| 23:01:05 to 12:57 next day, every 5 min | each pass: `nothing eligible (14 open, 0 candidate(s))`; c7 is read only for a candidate, so no pass named the dirt |
| 2026-11-21 12:57:41 | SEL-041 registered (`artifact_created` `696537cd`) |
| 13:02:21 | first refusal: `dirty_tree: c7,c17`, `dirty: uv.lock`, `unreconciled: uv.lock: not machine-written governed state (untracked)`; `dispatch_stuck` (threshold 1); `notify: sent` (the local banner) |
| before 13:07:32 | Desktop moved the file to `.seldon/quarantine_uv.lock_2026-11-21`; the 13:07:32 pass reads `dirty: (none)` |

So the stray file sat 14 hours 0 minutes unseen, and once a task was queued the alarm stood one pass (about 5 minutes)
before a person acted on it. The only signal was the local banner and the `dispatch_stuck` event. The gap SEL-044's
portfolio brief can carry: a tree's dirt is not reported while the queue is empty.
