# SEL-016: hazbrief adopts the standing dispatcher, and HB-70's paused work is committed so the dispatcher launches it

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-29, on the hazbrief Desktop thread's request.
**Repo:** seldon (primary, where the task is tracked); hazbrief-mcp (seldon.yaml gains its `dispatch:` block, the launchd plist is written and loaded, HB-70's paused work is committed on main). L4: commit, merge, push in both.
**After:** none
**Governing:** SEL-010R2 (`seldon dispatch adopt`, AD-038 ADDENDUM 05); SEL-005 (`docs/design/2026-09-15_standing_dispatcher.md`, "Adopting it in another project"); DN-006 decision 10 (no hand dispatch where a dispatcher runs); AD-034-R12 (cross-repo push). No new ruling expected.
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: one WIP commit in hazbrief, one `dispatch adopt` run, one plist load, one observed launch. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (writes hazbrief's seldon.yaml and loads a launchd agent)
**Parts:** A 0.35, B 0.45, C 0.20.
**Premises:**
- premise: hazbrief has no dispatch block | check: sh -c "! grep -q '^dispatch:' /Users/brock/GitHub/hazbrief-mcp/seldon.yaml"
- premise: the adopt command exists | check: grep -q "\"adopt\"" seldon/commands/dispatch.py
- premise: HB-70's paused work is still uncommitted on hazbrief main | check: sh -c "test $(git -C /Users/brock/GitHub/hazbrief-mcp status --porcelain | grep -c '^ M') -ge 9"
- premise: HB-70 ADDENDUM-02 exists and is superseded by Part A here | check: test -f /Users/brock/GitHub/hazbrief-mcp/cc_tasks/2026-10-29_HB-70_ADDENDUM_02_resume_in_the_primary_checkout_the_stderr_log_is_evidence.md

Checks are single commands with no shell.

## The condition

hazbrief has run every task by hand launch since 2026-10-20 because its seldon.yaml has no `dispatch:` block; the operator is the launcher. HB-70 (8d66641d, `After:` HB-69, completed) paused with its work uncommitted on main's working tree in the primary checkout (nine source and test files, 315 lines, plus its registration lines in `seldon_events.jsonl`). A dispatcher adopted now would refuse every task on c7 until that is committed, and a worktree launch from main would not see the work unless main carries it. So the order is: commit the paused work on main, adopt the dispatcher, let it launch HB-70.

## What to build

**A. Commit HB-70's paused work on hazbrief main, as it stands.** In `/Users/brock/GitHub/hazbrief-mcp` (the primary checkout, not a worktree): read `git diff --stat`; copy `logs/2026-10-29_sq052r_gate_stderr.log` to `docs/evidence/hb70/sq052r_gate_stderr.log` (ADDENDUM-02 item 3); commit every modified file, the evidence copy and the `seldon_events.jsonl` lines in one commit through the hooks with message prefix `HB-70 (wip):`, body naming ADDENDUM-01 item 4 as what remains. Run nothing else there; do not finish HB-70. Then write `cc_tasks/2026-10-29_HB-70_ADDENDUM_03_the_dispatcher_launches_hb70_from_main.md` in hazbrief, registered-file style, saying: the wip is on main at that commit; ADDENDUM-02 items 1 and 2 are superseded (the dispatcher launches HB-70 in a worktree from main, which carries the wip); item 3 is done; resume from ADDENDUM-01 item 4. Commit it through the hooks.

**B. Adopt.** `seldon dispatch adopt --project /Users/brock/GitHub/hazbrief-mcp --yes`, with `--standing-band-ref ../squiddy/squiddy/spend.yaml#job_token_cap_default` (the same reference seldon and squiddy use, never a number) and `--gate-command` set to hazbrief's test suite as its CLAUDE.md names it. Read seldon's own block first and carry each comment's reason; hazbrief's `environment:` names squiddy and seldon as siblings whose leases it respects if seldon's does. Commit the block and `.seldon/` changes through the hooks; load the plist; record the label and the first pass line from hazbrief's dispatch log.

**C. Observe one launch.** Wait for the first pass that lists HB-70 as a candidate and launches it (it is `After:` a completed task, so c18 is the only gate; grace is 0). Record the launch line, the worktree name and the log path in the RESULT. If the pass refuses HB-70, record the reason code and stop there; the refusal is the finding, not something to work around. Push hazbrief and seldon (AD-034-R12).

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M, or Part C's first pass whatever it says.

## Deliverables

A, B, C; `cc_tasks/2026-10-29_SEL-016_hazbrief_adopts_the_standing_dispatcher_and_hb70s_paused_work_is_committed_so_it_launches_RESULT.md`.
