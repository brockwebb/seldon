# SEL-025: the dispatcher cannot dirty its own tree: the rotated log is ignored, and an untracked filing is committed by the pass, not held against the queue

**Status:** proposed
**Author:** Desktop session (seldon), 2026-11-06. Measured here twice.
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-038-R1 (the machine reconciles its own state before c7); AD-038-R15 (the tool that writes a governed file commits it); AD-034 (the pass). Number new rulings under AD-038.
**Model:** primary
**Spend:** est. 0.2M tokens. Basis: one rename in a shell script, one ignore line, one sweep extension, two fixtures. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `scripts/jobs/seldon_dispatch.sh`, `.gitignore` and the pass's sweep)
**Parts:** A 0.40, B 0.60.
**Premises:**
- premise: the wrapper rotates the log to `<log>.<stamp>` | check: grep -q 'mv "$LOG" "$LOG.$(date' scripts/jobs/seldon_dispatch.sh
- premise: the ignore matches `*.log` only | check: grep -q '^\*\.log$' .gitignore
- premise: the sweep commits registered files only | check: grep -q "_commit_registered" seldon/commands/dispatch.py

Checks are single commands with no shell.

## The condition

The seldon queue was refused on c7 (`dirty_tree`) for every pass from 2026-11-04 02:19Z to 2026-11-06 12:55Z, three days, with SEL-023 and SEL-024 waiting. Two untracked files, both the machine's own:
1. `logs/seldon_dispatch.log.20261104T021957Z`, written by the wrapper's rotation (`scripts/jobs/seldon_dispatch.sh` line 74: `mv "$LOG" "$LOG.<stamp>"`); `.gitignore`'s `*.log` does not match a `.log.<stamp>` name. Second occurrence; the first (2026-10-28) was moved by hand under `logs/dispatch/`.
2. `cc_tasks/2026-11-02_FAC-03_filing_result_filename_convention_mismatch.md`, a consumer filing written into seldon by a dispatched factory session, never registered (it carries no headers; SEL-023 Part A is the registration path) and never committed. The pass's sweep commits registered task files only, so a filing sat as dirt and blocked the queue that would fix it.

Both are AD-038-R1's case: state the machine wrote, held against the machine. Each time, a Desktop moved or committed the file by hand; the operator runs nothing by hand.

## What to build

**A. Rotation that is ignored.** The wrapper rotates to `logs/dispatch/seldon_dispatch.<stamp>.log` (the `.log` suffix last) and the retention `find` follows; `.gitignore` gains `logs/**` under its reason. Fixture: a rotated name is ignored by `git check-ignore`.

**B. The pass commits a filing it finds.** The sweep that commits registered task files also commits an untracked `cc_tasks/*.md` whose header block declares `Kind: filing` or whose Status line says consumer filing, path-limited, as `dispatcher: filing: <basename>`, and lists it on the pass as `filing_committed`; it then shows as `filing` (SEL-023 A) rather than as dirt. Any other untracked path under a governed directory is still dirt and still refuses, with the path named on the pass line as today. Fixture: an untracked filing is committed by the pass and the next candidate launches; an untracked scratch file still refuses.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.3M.

## Deliverables

A and B with tests; ruling under AD-038; `cc_tasks/2026-11-06_SEL-025_the_dispatcher_cannot_dirty_its_own_tree_log_rotation_and_a_filing_left_untracked_RESULT.md`.
