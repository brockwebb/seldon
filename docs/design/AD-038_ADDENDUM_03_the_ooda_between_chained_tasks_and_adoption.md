# AD-038 ADDENDUM 03: the dispatcher waits for the Desktop OODA between chained tasks, and a project adopts it in one step

**Date:** 2026-10-26. **Status:** Accepted. Implemented by SEL-010R2
(`cc_tasks/2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`, task `09e3b92c`;
statement of record `cc_tasks/2026-10-25_SEL-010_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`).
**Amends:** DN-006 decision 2's criteria vector (as extended through c17 by AD-038-R9) with c18, and its candidacy
headers; `docs/design/2026-09-15_standing_dispatcher.md` ("Adopting it in another project"). Two new rulings,
numbered from the register.
**Code:** `seldon/core/dispatch.py` (`ooda_waits`, `ooda_index`, `ooda_file`, `evaluate` c18,
`first_refusal_reason`, `REFUSAL_REASONS`, `load_candidacy_headers`, `MINIMUM_HEADERS`, `candidacy`,
`parse_headers`, `load_dispatch_config`); `seldon/commands/dispatch.py` (`_ooda_waits`, `_tasks`, `_refusal_lines`,
`dispatch adopt`, `dispatch ooda pending|record`); `seldon/commands/dispatch_worktree.py`; `seldon/core/adopt.py`
(new); `seldon/core/reconcile.py` (the `_OODA.md` record is a task file); `seldon/core/stations.py` (the
`parts_undeclared` refusal); `seldon/mcp_server.py` (`seldon_ooda_pending`, `seldon_ooda_record`);
`scripts/jobs/seldon_dispatch.sh` (the project and plist as arguments).
**Tests:** `tests/test_sel010r2_ooda_gate_and_adopt.py`.
**Convention:** `docs/conventions/desktop_ooda.md` (the Desktop half of the loop).

## 1. Evidence

1. **A chain runs on its original premises.** The dispatcher closes the latency between a clean gate and a launch.
   Between task N's RESULT and task N+1's launch nothing reads the RESULT, names the premises it found wrong and amends
   N+1 (DN-006 §4: "post-completion decision latency ... is still the Desktop OODA, run when a Desktop thread opens";
   `docs/design/2026-09-15_standing_dispatcher.md`: "not automated here"). hazbrief's Desktop session authors these
   amendments by hand (`hazbrief-mcp/docs/design/2026-10-25_DN-011_ADDENDUM_00_d3_as_built.md`, "**Author:** Desktop
   OODA, from HB-41's RESULT"); a chain dispatched while the operator is away either ran every task on its first
   premises or waited for the person. The operator, 2026-10-25: the OODA should be built into the agentic process, not
   done by hand at the end.
2. **Adoption was by hand.** hazbrief had no `dispatch:` block, and adopting meant hand-writing the block, the band
   reference, the wrapper's log caps, the ignores and a plist. The candidacy headers were a constant
   (`REQUIRED_HEADERS`), and its third, `Framework layer served`, is ai-readiness-kg's DN-005 §5 rule 1, which every
   later adopter inherited by copying the constant.
3. **An addendum could not repair a committed task file's headers.** SEL-010's ADDENDUM-00 (9f4caa6) carried every
   header and `seldon cc register` still refused it `parts_undeclared`; SEL-010R then registered clean and was refused
   at every pass on c10. The only route was a new file, SEL-010R2.

## 2. Rulings

- **AD-038-R10. A chained task waits for the OODA on its completed predecessor, or the project's grace.**
  Criterion **c18**: a task with a `precedes` predecessor in `completed` or `verified` is eligible only once an OODA
  record for that predecessor exists or `dispatch.ooda_grace_s` seconds have passed since the predecessor's completion.
  The record is either an `ooda_recorded` event whose payload names the predecessor's id (`seldon dispatch ooda record
  <N>`, MCP `seldon_ooda_record`), or the file `<N's stem>_OODA.md` beside N's task file, counted only once committed
  (the successor's worktree is cut from main's HEAD); the reconciler commits an untracked one beside a registered task
  as it commits an addendum (AD-038-R1). The completion time is the ledger's last move of N into `completed`, else the
  graph's `updated_at` (an upper bound, so the grace is never shorter than declared); with neither, the task waits
  until a record (fail closed, like c14 and c17). A predecessor that ended `superseded`, `withdrawn` or `rejected`
  left no RESULT and holds nothing here. The grace defaults to 0, which never waits, and c18 is then absent from the
  vector; with a grace above 0, c18 is present for every task it applies to, passing or not, so `dispatch_launched`
  records what released it (`released_by`: `ooda_event`, `ooda_file` or `grace`). Its refusal reason is
  `ooda_pending`, printed with the predecessor, the grace left and the release line; a streak of it raises
  `dispatch_stuck` like any other, which is the signal that a Desktop OODA is due. `seldon dispatch ooda pending`
  (MCP `seldon_ooda_pending`) lists, for every completed predecessor without a record, the RESULT to read and the
  successor to amend. The reading itself is the Desktop's (`docs/conventions/desktop_ooda.md`).
- **AD-038-R11. The candidacy headers are a per-project list with a kit-wide minimum, read from the base file only,
  and a project adopts the dispatcher in one command.** `dispatch.candidacy_headers` names the headers a task file
  must carry to be a candidate; it must include `Spend` and `Network` (c4 and c5 cannot run without them) and may add
  any header of the project's own. Absent, it is `Spend`, `Network`, `Framework layer served`, the list every project
  read before, so no project's candidates change. The headers, like `**Parts:**` and `**Premises:**`, are read from
  the task's base file and never from an addendum: an addendum amends what a task does, and a candidacy read across
  files would need a precedence rule that registration, the stations and the Stop gate would all have to share. A
  committed file that lacks a header is re-filed as a new task file; the `parts_undeclared` refusal says so.
  `seldon dispatch adopt` writes a project's missing `dispatch:` keys (a key the project has is never rewritten; the
  machine-wide ones are copied from the kit's block in seldon's `seldon.yaml`; the band reference, branch and launchd
  label are asked, with defaults), `candidacy_headers` at the minimum, `ooda_grace_s: 0`, `enabled: false`, the
  wrapper's `jobs.dispatch` log caps, the ignore lines for the dispatcher's runtime state, and a launchd plist under
  `scripts/jobs/` that runs the kit's wrapper with the project and the plist as arguments, at a path it prints. It
  edits the configuration as text, keeping every comment, and validates the result with `load_dispatch_config` and the
  band's resolution before writing anything; `--dry-run` writes nothing.

## 3. Negative control

- `test_a_grace_of_zero_never_waits_and_c18_is_absent`: the default changes no vector.
- `test_a_predecessor_that_left_no_result_does_not_hold_its_successor`: superseded and withdrawn predecessors hold
  nothing.
- `test_the_ooda_file_releases_it_only_once_committed`: an uncommitted record does not release.
- `test_a_project_without_the_key_keeps_the_three_headers`: the header default is the old constant.
- `tests/test_dispatch_serial_transcript.py` is unchanged: its tasks have no predecessors and its project no grace.

## 4. What this does not change

- `precedes` (AD-029) and c2: c18 adds a wait after c2 is satisfied, never before.
- Cross-project waits (c17, AD-038-R8): a task waiting on another graph's task is not held by c18. The OODA on a
  chain that crosses projects is the waiting project's Desktop's, and it amends by addendum as usual; holding on it
  would need a record in the other project's ledger, which R8 forbids writing.
- The OODA's content. The dispatcher counts a record; it does not judge the reading.
- Any project's queue until that project sets `ooda_grace_s` above 0. seldon's own block leaves it at 0: a grace with
  no Desktop wake-up scheduled delays every chain by the grace and buys nothing (`docs/conventions/desktop_ooda.md`
  says what to schedule first).

## 5. Prior art

### External

- **Argo Workflows `suspend` template** (Argo documentation, "Suspending"): a step that pauses the workflow until
  `argo resume`, or until its `duration` elapses. *Decided here:* the record releases at once, the grace releases
  without one, and both are recorded.
- **Jenkins Pipeline `input` step within `timeout`** (Jenkins Pipeline steps reference): a human approval between
  stages, bounded by a timeout. *Decided here:* the grace is the bound, and it is the project's.
- **GitHub Actions environments: required reviewers and wait timer** (GitHub documentation, "Using environments for
  deployment"): a job waits for a review or for a fixed delay. *Decided here:* `0` means no gate, as an environment
  with no rule has none.
- **Boyd's OODA loop** (observe, orient, decide, act): the name of the step, already used in DN-006 §4. Orientation
  is the RESULT's reading; the decision is the addendum; the record is what the machine can count.

### Internal

- internal search (grep over docs/ and handoffs/ of seldon, squiddy, ai-readiness-kg, hazbrief-mcp, 2026-10-26):
  query "desktop ooda|ooda gate|ooda record|scheduled desktop|desktop wake" | hits
  `ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md:58` (the gap, named and left undesigned),
  `seldon/docs/design/2026-09-15_standing_dispatcher.md:15`, `hazbrief-mcp/docs/design/2026-10-25_DN-011_ADDENDUM_00_d3_as_built.md:4`,
  `hazbrief-mcp/docs/design/2026-10-25_DN-010_ADDENDUM_00_caller_supplied_values.md:4` (the OODA authored by hand).
  No earlier design of a gate or a record.
- AD-038-R9 (c17) is the shape adopted: a pass-level read of the ledger once, a criterion absent unless it applies,
  fail closed on an unreadable input.
- AD-038-R1 (the reconciler) is how a Desktop-written record is committed without a Desktop commit.
- AD-036 ADDENDUM 03 (prior art by reference) is the precedent for a project naming the kit's value rather than
  copying it; `adopt` copies the dispatcher's machine-wide values instead, as SEL-005 did, because `dispatch:` has no
  `ref:` form and the loader reads each key with its project's own reason beside it.
