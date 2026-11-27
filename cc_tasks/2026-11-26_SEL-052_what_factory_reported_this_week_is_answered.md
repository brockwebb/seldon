# SEL-052: what factory reported this week is answered

**Status:** proposed
**Author:** the factory coordinator (FCT-7, a Desktop session), 2026-11-26 21:05 EST. seldon is coordinated from the factory thread; what a project in use reports is seldon's next work (factory F-030 item 4).
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**What is known before this starts (from the filings; nothing re-measured by Desktop).** Read each in full first. They report; they do not prescribe. What changes is decided here.
- `cc_tasks/2026-11-26_filing_from_factory_spec_check_found_components_not_at_spec.md`, and factory's FAC-18 and FAC-21 RESULTs: `core.hooksPath` in a primary checkout is rewritten to an absolute path by something, after `seldon hooks install` set it relative, so `seldon verify` reports the commit hook as not installed (factory and critical-thinking-ai, 2026-11-26, twice).
- `cc_tasks/2026-11-26_filing_from_factory_the_prior_art_search_does_not_read_four_registered_repositories_and_a_need_stated_in_a_thread_cannot_enter_the_graph.md`.
- `cc_tasks/2026-11-26_filing_from_factory_a_return_task_waited_on_a_filing_that_never_runs_a_json_command_warns_on_stdout_and_the_mcp_portfolio_brief_shows_one_project.md`.
- `cc_tasks/2026-11-25_filing_from_factory_a_declared_worktree_link_to_a_tracked_directory_is_skipped_without_a_word.md`.
- `cc_tasks/2026-11-24_filing_from_factory_a_hold_that_waits_on_a_person_tells_nobody.md`.
- From the factory coordinator today, not yet a filing: a merge refused for one untracked placeholder directory (`merge_blocked: uncommitted_changes`, critical-thinking-ai CTAI-006R) sat for twenty minutes until a person looked; a return task (critical-thinking-ai CTAI-008, est. 0.05M to 0.1M, "nothing to build") ran for over forty-five minutes while extraction waited behind it. Read both tasks' logs and say what the time went to.
**Governing:** AD-036 (filings and returns), AD-038 (the dispatcher), AD-033. Where a fix needs a decision none holds, write it as an addendum to the governing note with its prior art and register record.
**Prior art:** from memory and UNVERIFIED unless confirmed and cited: a configuration value has one writer; alerts are raised on a state a person must act on, with its age (Google SRE, alerting on symptoms).
**Spend:** est. 1.4M tokens. Basis: SEL-050-class tasks; five filings and two observations, each with a reproduction.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.5, B 0.5.
**Premises:**
- premise: the spec-check filing is on main | check: test -f cc_tasks/2026-11-26_filing_from_factory_spec_check_found_components_not_at_spec.md
- premise: the prior-art filing is on main | check: test -f cc_tasks/2026-11-26_filing_from_factory_the_prior_art_search_does_not_read_four_registered_repositories_and_a_need_stated_in_a_thread_cannot_enter_the_graph.md

Glob and read every sibling `*SEL-052*ADDENDUM*.md`. Other repositories are read by path and never written. If the session passes 1.1M with items left, finish the one in hand and list the rest first in the RESULT.

## Part A: the hook path, the prior-art reach, the silent hold

Find what writes the absolute `core.hooksPath` (a red test), and make it stop. Answer the prior-art filing. A hold that waits on a person, a blocked merge included, reaches the dispatcher's `notify` with its reason and age.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- tests | grep -q ."` passes.

## Part B: the rest, and the returns

The return-task and worktree-link filings, and the two observations. A return task that has nothing to build completes without a session where the record allows it; if it cannot, say why. RESULT with `## For the consumer` per filing; `seldon cc return` for each filing answered.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-26_SEL-052_what_factory_reported_this_week_is_answered_RESULT.md"` passes.
