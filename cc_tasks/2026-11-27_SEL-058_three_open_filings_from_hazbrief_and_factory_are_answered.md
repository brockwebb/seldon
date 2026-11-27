# SEL-058: three open filings from hazbrief and factory are answered

**Status:** proposed
**Author:** the factory coordinator (FCT-7, a Desktop session), 2026-11-27 11:45 EST. seldon's queue was empty at the midday check.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**What is known before this starts (from the filings; nothing re-measured by Desktop).** Read each in full first, and the RESULTs of SEL-054, SEL-055 and SEL-057 so nothing is done twice. The filings report; what changes is decided here.
- `cc_tasks/2026-11-24_filing_from_hazbrief_a_parts_check_line_is_not_read_a_blocked_merge_was_completed_ungated_and_a_lease_wait.md`
- `cc_tasks/2026-11-27_filing_from_hazbrief_mcp_from_a_worktree_the_decision_register_reads_i.md`
- `cc_tasks/2026-11-27_filing_from_factory_declare_the_hive_in_seldon_s_dispatch_block_so_its.md`
- Also: `cc_tasks/2026-10-04_SEL-003_phase_1b_on_the_register.md` has sat open since 2026-10-04 with no Spend or Framework header, so it can never be a candidate. Say whether its work was overtaken (AD-033 and the register now exist) and withdraw or supersede it with the reason, or re-file what is left as an R-version.
**Governing:** AD-033 (the decision register), AD-034 (the merge gate; R26 on evidence), AD-038 (the dispatcher). A fix that needs a decision none holds is an addendum to its governing note with prior art and a register record.
**Prior art:** from memory and UNVERIFIED unless confirmed and cited: a command resolves its data from the checkout it is run in, never from a path baked at install (the worktree case); a gate that ran no check is not evidence (AD-034-R26 already holds this).
**Spend:** est. 1.0M tokens. Basis: SEL-052 answered five filings and two observations inside 1.4M.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.6, B 0.4.
**Premises:**
- premise: the worktree-register filing is on main | check: test -f cc_tasks/2026-11-27_filing_from_hazbrief_mcp_from_a_worktree_the_decision_register_reads_i.md
- premise: the Hive filing is on main | check: test -f cc_tasks/2026-11-27_filing_from_factory_declare_the_hive_in_seldon_s_dispatch_block_so_its.md

Glob and read every sibling `*SEL-058*ADDENDUM*.md`. Other repositories are read by path and never written.

## Part A: the two hazbrief filings

A red test reproducing each part that still holds at HEAD, then the fix. Parts already fixed by a later task are named with the commit.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- tests | grep -q ."` passes.

## Part B: the Hive declaration, SEL-003, and the returns

Do what the factory's filing asks of seldon's own repository if it is a declaration in `seldon.yaml` (read factory DN-005 and FAC-41's RESULT for what the declaration does). Dispose SEL-003. RESULT with `## For the consumer` per filing; `seldon cc return` for each filing answered.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-058_three_open_filings_from_hazbrief_and_factory_are_answered_RESULT.md"` passes.
