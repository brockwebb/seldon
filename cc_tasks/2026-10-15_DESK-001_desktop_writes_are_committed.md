# DESK-001: everything a Desktop session writes into a governed repo is committed by the tool that wrote it

**Repo:** seldon. L4: commit, merge, push.
**Date:** 2026-10-15. **Authored by:** Desktop session.
**Resolves:** ai-readiness-kg task 21af86f8 (filed 2026-09-22, parked, never run; it is superseded by this task) and the recurrence of the same stall on 2026-10-12, 2026-10-13 and 2026-10-14 (MODEL-003's RESULT; Issue 7e70aeb0; ai-readiness-kg tasks ba40cb29 and e2c4e125 refused for 126 passes on an untracked design note).
**Governing:** AD-030 (handoffs; R9 makes the design note the handoff's precondition), AD-036 (prior-art receipts), the dispatcher's c7 clean-tree criterion, d6a1f467 (a Desktop registration commits its own task file; the pattern this task generalizes).
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**After:** none
**Model:** primary
**Spend:** est. 1.2M tokens.
**Parts:** A 0.40, B 0.25, C 0.20, D 0.15.
**Part map:** A is the commit tool and registration; B is handoff and the dispatcher's visibility; C is tests; D is the ai-readiness-kg bookkeeping.
**Network:** none beyond git push.
**Exclusive:** yes

## Step 0

If this task is `in_progress`, stop. Otherwise set it `in_progress` now.

## The defect, measured

A Desktop session writes files through the Filesystem MCP: design notes, addenda, task files. It has no shell and no commit path. `seldon cc register` commits the task file it registers (d6a1f467) and nothing else. So every design note Desktop writes leaves the tree dirty; the dispatcher refuses every candidate for c7 on every 5-minute pass; `seldon go` shows `Lease: free` and nothing about why; the operator finds out hours later, reads the log, and commits by hand. Observed 2026-09-22 (DN-008, 92421acb, 3 hours), 2026-10-12 (MODEL-003, 36 hours, Issue 7e70aeb0), 2026-10-14 (DN-014 ADDENDUM 01, ba40cb29, 14 hours).

The principle: the tool that writes a governed file commits it. A write that leaves the tree dirty is a defect of the tool, not a chore for the operator.

## Part A: the commit path

1. **`seldon_commit_governed` MCP tool** (and `seldon commit-governed` CLI): takes a project dir and one or more paths; refuses any path outside `docs/design/`, `cc_tasks/`, `handoffs/`, `issues/`, `ontology/`; refuses a path the hooks reject (prior-art gate, protected paths) and returns the hook's reason verbatim; otherwise stages exactly those paths and commits through the hooks with a message of the form `desktop: <kind>: <basename>`. Never `git add -A`, never touches another session's files. Returns the commit sha.
2. **`seldon_cc_register` commits the design notes it names.** Every untracked or modified file under `docs/design/` that the task header references (Implements, Amended by, Governing, Resolves) is committed in the same commit as the task file, through the hooks. If a hook refuses one (no prior-art verdict), registration still registers the task and returns the hook's reason with the exact next command, as today, but it also says in one line that the dispatcher will refuse the task for c7 until that file is committed.
3. **A design note without a passing prior-art verdict can still be committed.** The AD-036 gate protects registration and dispatch, not the commit of a draft. If the commit hook currently refuses a design note for a missing verdict, change the hook so it refuses registration-time and dispatch-time only, and a draft note commits with a `draft:` marker in the message. Confirm against AD-036's text; if AD-036 says the commit itself must be gated, write the ruling change as an addendum (AD-036 ADDENDUM 04) with the three observed stalls as evidence.

## Part B: handoff and visibility

4. `seldon_handoff` commits every untracked or modified `docs/design/*.md` and `handoffs/*.md` it references before writing the handoff (21af86f8's fix 1).
5. `seldon go`'s Dispatcher section prints the last pass's per-candidate refusal line from the dispatch log: candidate id, criterion, dirty paths (21af86f8's fix 2). A blocked queue is visible at orientation.
6. The dispatcher's stuck notification fires on the first refused pass for c7, not after 10 minutes, and names the dirty paths in the notification body.

## Part C: tests (fake git where possible, real git in a temp repo where not)

- check: `seldon_commit_governed` on an untracked design note commits it and the tree is clean; on a path outside the allowed roots it refuses and nothing is staged; on a hook refusal it returns the hook's text.
- check: `seldon_cc_register` with an untracked design note named in `**Implements:**` commits both files in one commit.
- check: `seldon_handoff` with an uncommitted design note commits it before writing the handoff.
- check: `seldon go` with a refusal line in the log renders it in the Dispatcher section.
- check: removing the "stage exactly these paths" guard fails a test (AD-032 FC-27).
- check: full seldon suite, detached and polled; quote the counts.

## Part D: bookkeeping in ai-readiness-kg (absolute path `/Users/brock/GitHub/ai-readiness-kg`, read and graph only, no commits there)

7. `seldon task supersede 21af86f8 --superseded-by <this task's id>` with the reason "the Seldon-side fix; this task was filed in the wrong repo and parked". Do not touch any file there.

## RESULT

Under 40 lines: the tool's signature; what registration now commits; the AD-036 decision (hook changed or addendum written, with its id); the suite counts; the supersede edge; premises found wrong. `seldon verify`, `seldon cc complete`, merge, push.
