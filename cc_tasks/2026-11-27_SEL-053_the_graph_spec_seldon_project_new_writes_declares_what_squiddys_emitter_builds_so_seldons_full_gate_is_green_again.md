# SEL-053: the graph spec `seldon project new` writes declares what squiddy's emitter builds, so seldon's full gate is green again

**Status:** proposed
**Author:** the factory coordinator (factory OODA-003, a dispatched check-in), 2026-11-27. seldon is coordinated from the factory; a red gate is gate-time work (factory F-030 item 4).
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**Spend:** est. 0.4M tokens. Basis: one template, one test file, one decision addendum at most; SEL-051 (a RESULT only) measured 58k, and this adds a small code change and a targeted test run. The full suite is the merge gate's, not this session's.
**Network:** none beyond git.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Parts:** A 1.00.

## What is known before this starts (read by the factory coordinator; re-check it)

- seldon's merge gate for SEL-051 (`e32c45ea`) ran the full suite at 2026-11-27T03:43Z (`cadence_due`) and went red:
  `1 failed, 3601 passed, 8 skipped`, the one failure
  `tests/test_sel019_project_new.py::test_the_real_squiddy_initializes_a_filled_skeleton`
  (`logs/dispatch/2026-11-26_SEL-051_one_zero_token_session_start_prints_every_repository_s_state_including.gate.log`,
  line 73). SEL-051's branch changed one file, its RESULT, so the red is main's. SEL-051 is `merge_blocked`
  (`regate_red`) and its branch `worktree-lexical-jumping-spindle` is kept.
- SEL-052's RESULT ("Tests") already saw this failure and showed it fails identically on seldon main's code; nothing
  was filed for it.
- The cause: squiddy SQ-146 (`squiddy/cc_tasks/2026-11-26_SQ-146_init_refuses_a_spec_its_emitter_cannot_write_and_an_acquire_halt_from_a_missing_archive_directory_clears_when_the_directory_exists_RESULT.md`,
  Part A) made `squiddy init` refuse, on purpose and before writing anything, a spec whose emitter builds a class the
  spec does not declare for a kind the graph writes. For kind `work` those are Person, AuthoredBy, Organization and
  AffiliatedWith. seldon's skeleton, `seldon/templates/graph_spec/squiddy_graph.yaml`, declares only `- Work: Node`.
  So `graph_step` (`seldon/core/project_new.py`) writes a skeleton squiddy now refuses even after the operator fills
  title, description and scope. It then reports the refusal as "Fill ... title, description, scope.topic", which is
  wrong for this case.
- Reproduced by the coordinator on 2026-11-27 against seldon main and squiddy main:
  `python -m pytest tests/test_sel019_project_new.py -q -p no:cacheprovider -k real_squiddy`: 1 failed in 2.05 s,
  `squiddy init refused: FATAL: ... the emitter (emit.py) builds ['AffiliatedWith', 'AuthoredBy', 'Organization', 'Person'] for an entry of kind ['work'] ...`.
- Until this lands, every seldon merge whose gate runs the full suite is red, so no seldon task merges on a full gate.

## Part A: the skeleton squiddy accepts

1. Read SQ-146's Part A and squiddy's refusal text. squiddy's message names the two fixes: declare the four classes,
   or `write: {primary_class_by_kind: {work: null}}` for a graph that holds no Work. A graph made by
   `seldon project new` holds Works, so the first fix is the expected one. Decide and say why.
2. Prefer one source over a second copy that drifts again. If squiddy exposes its required classes or a default
   spec (for example what `init --check`'s `emitter-cannot-write` reads), consider reading that instead of
   hard-coding the four in seldon's template. Choose on the grounding and record the choice. If it is a decision
   none holds, write it as an addendum to the governing note (AD-037, which SEL-019 extended for `project new` as AD-037-R15, or whichever note holds it), with its
   register record.
3. Make `graph_step` report a refusal that is not about the unfilled fields as what it is: squiddy's own last line,
   with no "Fill title, description, scope.topic" advice. Write the red test first.
4. Run the targeted tests and anything else that reads the template. Do not run the full suite here: the merge gate
   runs it, and that run is what clears SEL-051.
5. In the RESULT, say whether any project already made by `seldon project new` carries the old skeleton. Such a
   project was initialized by squiddy before SQ-146, so `init` is not re-run on it. Name such projects; do not
   change them.

Do not: change squiddy, loosen SQ-146's refusal, skip or mark the test xfail, or redrive SEL-051. The factory's next
check-in redrives `e32c45ea` when this task is completed.

Acceptance:
- `check: /opt/anaconda3/bin/python -m pytest tests/test_sel019_project_new.py -q -p no:cacheprovider` passes.
