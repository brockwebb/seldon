# CC Task: Track `cc_tasks/` in the Seldon repo — execution records are provenance, not scratch

**Date:** 2026-09-02
**Authored by:** Desktop session
**Immutable once written. Before starting: glob and read all sibling `2026-09-02_track_cc_tasks_ADDENDUM*.md` files.**

## Context

`cc_tasks/2026-09-02_paper_build_xref_passthrough_failure_RESULT.md` notes that `cc_tasks/` is gitignored in this repo, so the RESULT for a fix to the Seldon build stays on one disk. Every project Seldon manages tracks `cc_tasks/` on purpose (ai-readiness-kg CLAUDE.md: "`cc_tasks/` is intentionally tracked; `handoffs/` is not"). The system that enforces provenance on other projects is the one repo whose own execution records are unversioned. Decision: track them, unless step 1 finds a reason not to.

## Steps

1. `git log -p --follow .gitignore` for the line that ignores `cc_tasks/`; restate the commit and its message. If the commit or a design doc gives a reason (secrets, size, an explicit decision), stop and report it in the RESULT instead of proceeding.
2. Scan every file under `cc_tasks/` for credentials, tokens, absolute paths outside `~/GitHub`, or anything over 1 MB. Report findings. Do not commit any file that carries a secret; list it and leave it ignored by an explicit negative pattern.
3. Remove the ignore line. `git add cc_tasks/`. One commit for the tracking change and the historical files together, message stating that the files are being versioned retroactively and that their dates predate this commit.
4. Update `CLAUDE.md` in this repo with the same sentence ai-readiness-kg uses: `cc_tasks/` is intentionally tracked; `handoffs/` is not.
5. `seldon verify` and the full suite (dotenv form) unchanged.

## Constraints

Zero model calls. No database touched.

## Completion

RESULT at `cc_tasks/2026-09-02_track_cc_tasks_RESULT.md` (now tracked); `seldon cc complete`; commit and push.
