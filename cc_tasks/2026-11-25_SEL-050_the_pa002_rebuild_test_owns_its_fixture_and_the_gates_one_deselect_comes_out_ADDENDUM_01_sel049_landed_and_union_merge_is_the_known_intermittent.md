# ADDENDUM 01 to 2026-11-25_SEL-050_the_pa002_rebuild_test_owns_its_fixture_and_the_gates_one_deselect_comes_out: SEL-049 landed; `union_merge` is the full tier's one known intermittent

**Author:** OODA knowledge source on efcdcf91 (AD-038-R16)
**Source:** `cc_tasks/2026-11-25_SEL-049_the_gate_runs_in_parallel_and_the_dispatcher_timing_tests_wait_on_a_condition_RESULT.md`, Parts B and C; `docs/evidence/sel049/`.

## What SEL-049 changed for this task

1. **The guard is met.** SEL-049 landed as written: `seldon.yaml` `dispatch.gate_command` now ends
   `-p no:cacheprovider -n 6` followed by the pa002 `--deselect` line. The premise (`deselect tests/test_pa002...`
   still present) holds at HEAD. Proceed past "Before any other work, confirm it".
2. **The comment block Part B step 1 edits has grown.** Above `gate_command` there are now two comment paragraphs:
   the SEL-045R/Issue `d6040ce8` paragraph that explains the deselect, and SEL-049's `-n 6` paragraph (measured
   basis, pytest-randomly). Remove only the deselect's paragraph and the `--deselect` line; keep SEL-049's paragraph
   and the `gate_timeout_s` comment below unchanged.
3. **The measured cost of Part B step 2 and of this task's merge gate.** SEL-049's own `-n 6` full run took
   1,573 s (26:13) quiet-ish; SEL-047 loaded runs took 2,193 to 2,508 s. The task's "26 to 42 minutes" stands.

## `union_merge` in Part B step 2

SEL-049's one full `-n 6` run failed exactly one test,
`tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`
(`merge_blocked`, `main_kept_moving` after 3 attempts: record commits for both tasks moved main while b merged).
It failed 0 of 10 alone in SEL-049 and 2 of 20 alone in SEL-047. Its fix is under `seldon/` and belongs to a
separate task; it is not this task's to diagnose or fix.

Part B step 2's rule is unchanged: the run is green, or the RESULT names every failing id and does not claim green.
What this addendum adds:

- If `union_merge` is a failing id, quote its assertion message (states, `merge.reason`, `attempts`) into
  `docs/evidence/sel050/full_run.txt` beside the tail, and say in the RESULT whether its reason is again
  `main_kept_moving`. That is one more data point for its fix task.
- Do not re-run the whole suite to chase a green, and do not edit `tests/test_dispatch_parallel.py` or anything under
  `seldon/`.
- Any **other** failing id is a finding of this task and is named as the task says.
