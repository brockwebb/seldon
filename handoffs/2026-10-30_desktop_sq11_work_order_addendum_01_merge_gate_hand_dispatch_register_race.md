# Addendum 01 to the 2026-10-28 squiddy SQ11 work order: three more measured defects, all dispatcher-side

**From:** the squiddy Desktop session SQ11, 2026-10-30. **Amends:** `handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md` (W1 to W5 stand). Nothing here is registered in seldon's graph; the seldon Desktop session registers what it takes.

## W6. The merge gate does not enforce R-188 (a kit pass per kit commit)

Measured twice on squiddy main:
- Between the 2026-10-27 pass (`bc345c09`, passes.jsonl line 23) and SQ-099's pass (`d31501c7`, 2026-10-29), four tasks merged with no kit record. SQ-099's RESULT documents it. During that window the "environmental" label hid three real code-gate findings that blocked every green pass.
- SQ-101 (6e639ee8) merged at `67cde2da` on 2026-10-30 with no kit record. Its RESULT reports 17 failures it classifies as worktree-environmental and that ruff is not installed in the kit's `.venv`, so no lint ran. Main's last pass line is still SQ-100's `8e3e9bce`.

squiddy's DN-043 R-188 requires a pass per kit commit; DN-052 R-237 makes the pass ledger main's. The dispatcher's merge gate accepts a branch whose RESULT says green-except-environmental. Either the merge gate requires a `kit record-pass` line for the tip it merges (preferred: the pass already runs in a shared clone where the worktree-only failures do not occur, SQ-099 measured 2,549 of 2,549), or R-188 is amended to say what the dispatcher actually enforces. One of them changes; a ruling that the gate does not enforce is a dirty bit.

## W7. "Hand-dispatched" is not a header the dispatcher honors

SQ-050RM (e1df72ef) was registered as hand-dispatched (it fast-forwards main, SEL-004 decision 3), and a `blocked` state with that reason was set within two minutes of registration. The dispatcher launched it before the block landed. The session handled it correctly (it replayed onto a branch instead of fast-forwarding), but the protection was luck. A header such as `**Dispatch:** hand` that registration records and the dispatcher refuses (c-criterion) closes it; a task that needs a cross-tree operation then cannot be picked up by a worktree session.

## W8. Write-then-register races the dispatcher

Two occurrences on 2026-10-30 in squiddy: a Desktop wrote a task file, then registered it about a minute later; the dispatcher's 5-minute pass in between saw an untracked file and refused every task on c7 (`dirty_tree`) for one pass. SQ-050R's `spec_modified` merge block (2026-10-28) is the same class in reverse: registered at one commit, edited before dispatch. Fix candidates, either one: `seldon cc register` takes the file content and writes plus commits it in one call (the file never exists untracked); or registration refuses any later edit to a registered file except through an ADDENDUM, and the dispatcher reads the registered hash's bytes. This joins W2 (mechanical refusals retried under a rule).

## For the record, not a seldon item

The two hazbrief return tasks SQ-100 and SQ-101 filed themselves (HB-77, HB-79), registered in hazbrief's graph, are the first instances of W3's rule run by a task rather than by a Desktop.
