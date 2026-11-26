# SEL-050: the pa002 rebuild test owns its fixture, and the gate's one deselect comes out

**Status:** proposed
**Author:** Desktop session (factory coordinator, FCT-4), 2026-11-25 22:55 EST, from SEL-047's RESULT and `docs/evidence/sel047/README.md` Parts C and E item 3. Closes Issue `d6040ce8`'s first test.
**Repo:** seldon only. squiddy is read and its kit is called, never written. L4: commit on the task branch; the dispatcher merges.
**After:** 2026-11-25_SEL-049_the_gate_runs_in_parallel_and_the_dispatcher_timing_tests_wait_on_a_condition
**Governing:** AD-036-R2 and R3 (AD-036 ADDENDUM 06, PA-002: a library receipt verifies against the release it names); AD-034-R29 to R37. No new ruling.
**Gate:** full
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: SEL-047 Part C already read the test and the code it reaches; this builds one small fixture inside one test file, edits one configuration line, and runs the file and one whole suite at `-n 6`, detached and polled. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.6, B 0.4.
**Premises:**
- premise: pa002 is still deselected by name | check: grep -q "deselect tests/test_pa002_release_resolve.py" seldon.yaml

## Why, and this task's own gate

`tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` reads squiddy's live library on the operator's disk, so its outcome depends on another repository's state. It has been red on main since 2026-11-09 and is deselected from `gate_command` by name. SEL-047 Part C found that no squiddy check asserts the same property, so the test cannot leave the gate for one; it has to own what it reads.

This task runs after SEL-049, which puts `-n 6` into `gate_command`. **Before any other work, confirm it:** `grep -A3 '^  gate_command:' seldon.yaml` shows `-n 6`. If it does not, SEL-049 did not land as written: stop and say so in the RESULT. This task changes `gate_command`, so it plans **full** (`gate_config_changed`) and its merge runs main's command, at `-n 6`: about 26 to 42 minutes of lease, once.

Read `docs/evidence/sel047/README.md` Part C in full first. Runs longer than two minutes are detached under `caffeinate -i` and polled.

## Part A: the test builds the small library it rebuilds

1. In `tests/test_pa002_release_resolve.py` only: the test builds, inside `tmp_path` and with the kit's own calls, a small served release (a handful of rows and one dense shard set), then rebuilds it through the older-release path and asserts what it asserts today: the rebuild reproduces the served index's rows and shard set exactly. No file is committed under `tests/fixtures/`. The seldon code path exercised is the same one SEL-047 Part C names; say which in the RESULT.
2. If the kit cannot build a served release that small without the operator's library or a model call, stop at this step: write what it needs in the RESULT, leave the deselect in place, and do not attempt Part B. That is a finished task with a finding.
3. Keep the live comparison available by hand (a marker or an environment switch, off by default), since SEL-047 found it red for a real reason: the same 416,365 rows with a different row fingerprint and shard set. Do not investigate that here.
4. Run the file five times; all pass.

Acceptance:
- `check: sh -c "python -m dotenv -f \"$SELDON_PRIMARY_CHECKOUT/.env\" run -- env PYTHONPATH=. python -m pytest tests/test_pa002_release_resolve.py -q -p no:cacheprovider"` passes.

## Part B: the deselect comes out

1. `seldon.yaml`: remove the `--deselect` line from `dispatch.gate_command` and the comment that explains it; leave one line citing this task and Issue `d6040ce8`.
2. One whole-suite run with the command exactly as `gate_command` now reads, detached; record its tail in `docs/evidence/sel050/full_run.txt`. It is green, or the RESULT names every failing id and this task stops without claiming green.
3. The RESULT says what remains of Issue `d6040ce8` (it is resolved by factory, not here) and whether the live comparison is still red.

Acceptance:
- `check: sh -c "! grep -q 'deselect tests/test_pa002' seldon.yaml"` passes.
- `check: grep -q -E "passed" docs/evidence/sel050/full_run.txt` passes.
