# SEL-062: the dispatcher's limits, passes and merge evidence hold what their rulings say

**Status:** proposed
**Author:** REVIEW-001 (a dispatched session that did not write the reviewed code), 2026-11-28, from its findings record.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** 2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc
**Found in:** seldon:docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md#F-05
**Governing:** AD-038 (R40 the coordination lane, R43 the minted identity, R44 the session guard, R45 the planted controls), AD-034 (R26 evidence, R38 and R39 the scheduled gate and its closure, R41 completion of a blocked task), AD-037. A change to a ruling is an addendum with prior art and a register record, `seldon prior-art verify` passing before code.
**Prior art:** named per finding in the review record: least privilege and complete mediation (Saltzer and Schroeder 1975) for the guard; NIST SP 800-53 CA-2/CA-8 for controls that are tried; pipes and filters for one pass pipeline; guard conditions on state-machine transitions (UML/Harel statecharts) for R41. Read the review record first; it carries the evidence lines.
**Spend:** est. 1.5M tokens.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.4, B 0.35, C 0.25.

REVIEW-001 found these in the code merged between e42c25bc and 078b80d0 (`**Found in:**` names the first; this task remediates F-05 to F-22, each an Issue). It fixed only the classes it may fix (F-01 to F-04: the scheduled checkout's removal and three holes in R41). Everything below is the rest of the dispatcher's findings, grouped. Each finding is an Issue (`seldon issue list --type review_finding`); a fix names its finding's Issue and carries a test that fails first.

## Part A: the limits and their controls (F-05, F-06, F-22)

- F-05: a harness error in a planted control (a hook call over `HOOK_TIMEOUT_S`) is recorded as a limit that did not refuse, and the controls are re-tried only when the limits' fingerprint changes, so one slow call refuses every launch until `seldon.yaml` changes; `seldon dispatch controls` does not write the state that would clear it; and the fingerprint leaves out the code that enforces the limits (`seldon/core/controls.py:164`, `seldon/commands/dispatch.py:2721`, `seldon/core/controls.py:225`).
- F-06: the session guard is a substring test over tool inputs. REVIEW-001's probe: a `cd <parent> && cat <relative>`, a quote-split spelling and a Grep rooted at the parent directory all pass it (`seldon/core/controls.py:112-136`). R44 says the guard stops a session's ordinary reach; these are ordinary reach. Decide, in an addendum to AD-038, between an OS-enforced deny (Claude Code's sandbox filesystem deny rules, or a separate Unix user for sessions) and narrowing R44's claim; plant the bypass spellings as controls whichever way it goes.
- F-22: a failed mint's stderr tail is recorded in the `session_identity` event, which is committed and pushed (`seldon/core/hive.py:101-103`). Scan it or drop it.

Acceptance:
- `check: python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -k "sel062 and part_a"` passes.

## Part B: the passes (F-07, F-09 to F-15, F-17, F-18, F-20)

- F-15 is the root of F-07 and F-13: the serial pass and the parallel pass are two hand-maintained implementations, and the lane's launch is a third. The held alarm is called only in the serial pass (F-07, `seldon/commands/dispatch.py:1488`, `:1553`); the status views plan without the lane (F-13, `seldon/commands/dispatch.py:246`, `seldon/commands/dispatch_worktree.py:367-373`). One pass pipeline, with launch policy as the variable, or a recorded reason not to.
- F-09: lane membership is matched against the file's own name (`seldon/core/lane.py:86-88`), so any filer joins the lane by naming the file.
- F-10: a lane candidate skips the resource-overlap check, and running lane rows hold nothing for others (`seldon/core/dispatch.py:663-680`); R40 exempts lane tasks from exclusive holds only.
- F-11: in a serial lane project a running lane session is not the claim in flight, so the scheduled gate can run while it does (`seldon/commands/dispatch.py:1497-1501`, `:1566`).
- F-12: `dispatch_gate.maybe_run` says it never raises but catches only `ScheduledBusy` and `GateConfigError` (`seldon/commands/dispatch_gate.py:189-197`).
- F-14: the comment at `seldon/commands/dispatch_worktree.py:337` states an invariant the lane removed.
- F-17: the event store (about 20 MB) is parsed in full several times per pass; read it once per pass.
- F-18: since SEL-055 only a dispatcher pass runs the full suite; nothing shows how old the newest full gate is when no pass runs (`seldon/core/gate_plan.py:543`).
- F-20: the `environment_in_flight` alarm went from 3 passes to 12 for consumers that do not name it, with no measured basis (`seldon/core/dispatch.py:761-763`). An erratum and the effective threshold in `dispatch status`.

Acceptance:
- `check: python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -k "sel062 and part_b"` passes.

## Part C: merge and completion evidence (F-08, F-16, F-19, F-21)

- F-08: `seldon cc return` writes `check: test -f <its own RESULT>` into every return, and the finish already requires that RESULT, so the Stop gate's one check always passes and counts as merge evidence under R26 (`seldon/core/returns.py:484-490`, `seldon/commands/dispatch_worktree.py:915-917`).
- F-16: R41 is enforced at the completion entry points (REVIEW-001 put both on one function) and not as a guard on the `blocked` transitions themselves; R45 keeps its own standing-condition file. Decide whether guards move onto the state machine.
- F-19: a declared `gate_record` is admitted under the closure and clears a red main even when scoped by `tree_paths` (`seldon/core/gate_plan.py:341-354`, `:423-431`); R39 ends the closure on a full pass.
- F-21: R41's evidence is a passing full gate of main's tree; nothing checks that the blocked task's branch is on main.

Acceptance:
- `check: python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -k "sel062 and part_c"` passes.
- `check: test -f cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say_RESULT.md` passes.

**This task may not:** touch another repository, or change a ruling without its addendum and register record.
