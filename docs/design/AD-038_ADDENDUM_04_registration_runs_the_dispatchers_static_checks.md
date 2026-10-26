# AD-038 ADDENDUM 04: registration runs the dispatcher's static checks, and every non-candidate gets a reason line

**Date:** 2026-10-26. **Status:** Accepted. Implemented by SEL-011
(`cc_tasks/2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason.md`,
task `bd5f26fb`).
**Amends:** AD-038-R5 (registration runs the task's premises), which this extends from premises to the candidacy
checks; DN-006 decision 2's candidacy (headers) and c4; AD-038-R11 (the base file is the only file read).
**Resolves:** ResearchTask `9965fbed` ("a task that is NOT A CANDIDATE gets no reason line").
**Code:** `seldon/core/dispatch.py` (`static_checks`, `static_refusal`, `candidacy`, `evaluate`,
`first_refusal_reason`, `REFUSAL_REASONS`, `LAYER_GRAMMAR`, `SPEND_GRAMMAR`); `seldon/commands/cc.py`
(`registration_static_refusal`, `register_task_file`); `seldon/commands/dispatch.py` (`_refusal_lines`,
`dispatch status`).
**Tests:** `tests/test_sel011_registration_refuses_what_dispatch_would_refuse.py`;
`tests/test_dispatch_launch.py::test_a_pass_with_nothing_eligible_writes_no_event`.

## 1. Evidence

The criteria were applied at two points by two code paths, and a file could pass the first and never run:

1. SEL-010 (hazbrief, 2026-10-25): committed with no Parts, a non-numeric Spend and no framework-layer header.
   Registration refused on Parts only; the other two would have refused it at dispatch.
2. SEL-010R (2026-10-26): registered clean, then refused at every pass on c10 `concurrency_undeclared`
   (`Exclusive: no` with no `Touches`). Withdrawn and re-filed as SEL-010R2.
3. squiddy SQ-088 and SQ-091: two days `proposed` while each pass printed "0 candidates" and no reason, because the
   files carried none of Spend, Network and Framework layer served.
4. `9965fbed` (filed 2026-10-15 from ai-readiness-kg `fb3b11bc`, evidence 2026-09-22): `_refusal_lines` printed a line
   only for a candidate, so a not-a-candidate reason reached `seldon dispatch status` and never the pass log or
   `seldon go`. Seven hours of "0 candidate(s)" on an unparseable Framework-layer value.

## 2. Ruling

- **AD-038-R12. Registration refuses on every static candidacy check the dispatcher applies, by the dispatcher's own
  function, and every pass names each non-candidate.** `seldon.core.dispatch.static_checks` is the one function both
  `evaluate` and `seldon cc register` call. Its checks read only the task's base file and the project's configuration:
  the `dispatch.candidacy_headers`, the Framework-layer value, Spend as `zero` or a token count, the Network grammar,
  Exclusive/Touches (c10), the Model lock, `**Parts:**` under the project's Parts baseline, and the After grammar.
  Registration refuses on any failure, naming every failure at once as `<reason code>: <grammar or rule>`, before
  anything is created. A project with no `dispatch:` block is held only to the checks registration applied before
  (Model lock, Parts, After); a `dispatch:` block that does not load refuses (`dispatch_config_unreadable`). What
  depends on live state stays dispatch-only: c4's comparison with the band, c2, c6, c7, c11 to c18. At the dispatcher,
  Spend, Network and Exclusive/Touches remain criteria (c4, c5, c10), so a file that fails one keeps its refusal line
  and its `dispatch_stuck` streak; the rest make the file not a candidate, and Parts and After are new reasons there
  (`parts_undeclared`, `after_unresolved`). An unparseable Spend is refused as `spend_unreadable`, not `above_band`.
  Every pass prints one line per non-candidate (`<id> not_a_candidate: <reason>  <source file>`, with the grammar
  under it) beside the lines for refused candidates, so "nothing eligible (N open, 0 candidates)" is followed by N
  lines, in the launchd log and in `seldon go`'s last-pass view; `seldon dispatch status` prints the grammar under its
  `NOT A CANDIDATE` line.

## 3. Negative control

- `test_a_clean_file_passes_both`: a file that carries every header registers and is eligible.
- `test_a_project_without_a_dispatcher_is_held_only_to_what_registration_always_applied`: a project that never adopted
  the dispatcher gains no refusal on headers it was never asked for.
- `tests/test_dispatch_serial_transcript.py` is unchanged: a candidate's criteria vector and its refusal lines are the
  same bytes.

## 4. What this does not change

- The headers are still read from the base file only (AD-038-R11). A committed file whose headers are wrong is
  repaired by a new task file; an addendum cannot supply one, at registration or at dispatch.
- The band. Registration does not hold Spend against it: the band is a live reference (`standing_band_ref`) that can
  move between registration and the pass.
- Already-registered tasks. Parts and After are now read at the dispatcher, but every task registered since QC-002 was
  refused on both at registration, and baseline tasks are exempt from Parts as before.

## 5. Prior art

### External

- **Slurm: submission-time validation and the pending REASON.** `sbatch` rejects a job whose specification is invalid
  at submission ("Batch job submission failed: ..."), and `squeue` prints a REASON for every pending job (`Resources`,
  `Priority`, `Dependency`, `InvalidQOS`, ...) (Slurm documentation, `sbatch(1)`, `squeue(1)` "JOB REASON CODES").
  *Adopted:* refuse at submission what the scheduler would never run, and give every pending job a reason code.
- **Kubernetes: admission validation before scheduling, and the unschedulable condition.** The API server validates
  an object's spec at create time (validating admission), and a pod the scheduler cannot place carries a
  `PodScheduled=False` condition with a reason and message (Kubernetes documentation, "Admission Controllers",
  "Pod Lifecycle: Pod conditions"). *Adopted:* static validation at the front door, live conditions at the scheduler;
  the split here is the same (static checks at registration, band, tree and leases at the pass).

### Internal

- AD-038-R5 (FRICTION-001 Part E): registration runs the task's `check:` premises so a false one reaches its author in
  the same turn. The precedent this extends.
- AD-037-R6 (c), QC-002: the Parts check already ran at registration (`stations.parts_registration_refusal`); it is
  now called from `static_checks`, so the dispatcher reads it too.
- `9965fbed`'s own fix text: "one line per excluded proposed task naming the header and quoting its grammar, as
  `network_undeclared` already does". Done, and the Framework-layer grammar is now a constant beside
  `NETWORK_GRAMMAR` (`LAYER_GRAMMAR`). Writing it into DN-006 (ai-readiness-kg) is that repository's, not this task's.
