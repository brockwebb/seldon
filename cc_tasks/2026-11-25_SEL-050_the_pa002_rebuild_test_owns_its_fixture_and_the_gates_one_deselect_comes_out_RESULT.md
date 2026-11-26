# RESULT: SEL-050. The pa002 rebuild test builds the library it rebuilds, and the gate deselects nothing

- **Part A done.** `test_rebuilding_the_served_release_reproduces_the_served_index` now builds a small served release
  in `tmp_path` with squiddy's own calls: 3 entries, 7 rows, 3 dense shards, a stub encoder, about 0.2 s. It rebuilds
  that release through `seldon.core.prior_art.rebuild_release` and asserts the same three things as before: rows,
  `row_fingerprint` and `shard_set_sha256` equal the served index manifest's. Nothing is committed under
  `tests/fixtures/`. The file passed **5 of 5** runs (10 passed, 1 skipped each). A planted defect (the rebuild drops
  one row) makes the test fail.
- **The live comparison is kept and is off by default.** It is `test_rebuilding_the_live_served_release_reproduces_the_live_served_index`,
  run with `SELDON_PA002_LIVE=1`. **It is still red**, with the same values SEL-047 recorded: rebuilt `7a774aec…` against
  served `b8103764…`. I did not investigate it (task Part A step 3).
- **Part B done, green.** The `--deselect` line and its comment paragraph are gone from `dispatch.gate_command`, and
  one line cites SEL-050 and Issue `d6040ce8`. I ran the command once, exactly as it now reads (`-n 6`): **3,560
  passed, 8 skipped, 0 failed in 1,540 s (25:40)**, EXIT 0. `union_merge` passed in this run.

**Date:** 2026-11-26 (EST). **Branch:** `worktree-zazzy-marinating-goblet`, from main `60dd9a5`. Part A commit
`736a6eb`; Part B and this RESULT are in the commit after it. This session did not merge, push or complete the task.
**Addenda read:** ADDENDUM 01 (SEL-049 landed; `union_merge` is the known intermittent). Its guard held:
`gate_command` read `-n 6` before any work. Following the addendum, only the deselect's paragraph was removed;
SEL-049's paragraph and the `gate_timeout_s` comment are unchanged.
Recall used: none

I read the recall hits. SEL-047's content reached this task through `docs/evidence/sel047/README.md` Part C, which
the task names, so it is not counted as a recall hit. The SQ-139 hit is about `build_db`'s default columns, which
this task does not touch. The prior art that did shape the fixture was squiddy's own test
`tests/test_sq139_release_receipt_stage.py` and its helpers in `tests/test_s016_index.py`. They already build a tiny
indexed graph with releases and run seldon's `rebuild_release` on it. I followed their steps with the kit's public
calls; I did not import squiddy's `tests` package.

Changed: `tests/test_pa002_release_resolve.py` (its last section and the module docstring), `seldon.yaml` (the
deselect and its comment), `docs/evidence/sel050/**`, and this RESULT. Nothing under `seldon/`. Nothing in squiddy
was written. Zero model calls, no network. Nothing was filed and nothing was registered.

## Part A: the fixture

**The seldon code path exercised** is the one SEL-047 Part C names: `prior_art.rebuild_release(graph, sha256, work)`.
It runs `_release_rows`, which does four things: `release_commit` on the export register; the corpus manifest and
`index:` block at that commit, through `git show`; the same-`index:`-block check against today's; and
`checkpoint_rows`, which goes to `squiddy.index.iter_rows` under arm A's rule because the installed kit has no
`release_rows`. `rebuild_release` then runs `squiddy.index.build_db`, picks each entry's keyed dense shard by
`unit_key`, verifies it by hash and row ids, and computes `row_fingerprint` and `shard_set_sha256`. The only change
from the live test is the input: the graph `pa.Library(s).graph()` loaded from squiddy's library on disk is replaced
by a graph built in `tmp_path`.

**How the kit builds it** (`_served_fixture_release`):

1. `squiddy.init.render_config` and `render_manifest` produce the graph's `config.yaml` and its empty manifest from
   a one-paragraph spec. That spec declares the metadata document in its `emit:`. `init.write_graph`, the full
   `squiddy init`, could not be used here: it also generates LinkML artifacts with `gen-pydantic`, which is not
   installed in seldon's interpreter (`FileNotFoundError: /opt/anaconda3/bin/gen-pydantic`). The index never reads
   those artifacts. This is the one departure from "the kit's own calls" for the whole graph.
2. Three manifest entries go in the graph's in-graph stage. Two have texts (one with two pages) and one has none.
   The `index:` block uses a four-dimension stub encoder, with values from squiddy's `tests/test_s016_index.py`.
3. `git init`. The export file and its `EXPORT_VERSIONS.md` row are committed as release v1.
4. `squiddy.index.build(graph, encoder=stub, read_pages=..., release=export, reader=stub identity)` writes the
   checkpoint, the database, the keyed shards and the served `index_manifest.json`. That manifest names the release's
   export and sha256, as the library's does.
5. `squiddy.index.build_corpus_rows(...)` runs with its default rule (arm A's `q003-corpus/1`) and writes the same
   units' checkpoint lines the way arm A writes them. The reason: since SQ-028R a paragraph index's own lines are
   keyed `sq028r-corpus/2:pages:...`, while seldon reads arm A's lines until the kit has `release_rows`
   (AD-036-R30). The library's checkpoint holds arm A lines (squiddy SQ-139: 2,357 of them on 2026-11-13).
   Squiddy's own SQ-139 fixture copies its lines with the rule renamed; this fixture writes them with the kit's
   writer instead. Once the kit has `release_rows`, `checkpoint_rows` calls it and these lines are not read.

Part A step 2's stop condition did not apply: the release needs neither the operator's library nor a model call.

**Sensitivity check** (`/tmp` script, not committed). With `build_db` wrapped inside `rebuild_release` so that it
drops the last row, the test fails with `AssertionError`. Unmutated, it passes.

**Evidence:** `docs/evidence/sel050/pa002_file_five_runs.txt` has five runs of the acceptance command, each
`10 passed, 1 skipped`, pytest exit 0. `docs/evidence/sel050/live_comparison.txt` has the switched-on live run.

## Part B: the deselect comes out

`seldon.yaml`: removed the four comment lines of SEL-045R's paragraph and the
`--deselect tests/test_pa002_release_resolve.py::...` line, and added
`# SEL-050, Issue d6040ce8: nothing is deselected; the pa002 rebuild test builds its own library (live run by hand).`
`gate_command` now parses to
`python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -n 6`.

**The whole-suite run** used that command, read from `seldon.yaml` by `docs/evidence/sel050/run_gate_command.sh`,
detached under `caffeinate -i` and polled to its EXIT line. It ran from 02:44:43 to 03:10:25 EST, with load
averages of about 15 to 25. Result: `3560 passed, 8 skipped in 1540.46s (0:25:40)`, EXIT 0. No test failed, so
there is no `union_merge` message to quote and no `main_kept_moving` data point from this run. Compared with
SEL-049's run, passed went from 3,558 + 1 failed to 3,560. The difference is the fixture test, which no longer
needs a deselect, and `union_merge` passing. Skipped went from 7 to 8; the new skip is the switched-off live test.
Tail: `docs/evidence/sel050/full_run.txt`.

Acceptance checks, run here:
- `sh -c "! grep -q 'deselect tests/test_pa002' seldon.yaml"`: exit 0.
- `grep -q -E "passed" docs/evidence/sel050/full_run.txt`: exit 0.
- Part A's `sh -c "python -m dotenv ... pytest tests/test_pa002_release_resolve.py -q -p no:cacheprovider"`: exit 0
  (five times).

**Merge cost.** This task changes `gate_command`, so its merge plans the full tier and runs main's command at `-n 6`
once: about 26 minutes quiet, about 42 loaded (SEL-047, SEL-049, and this run's 25:40).

## What remains of Issue d6040ce8, and the live comparison

- **The Issue's first exit is done in seldon.** The test owns its fixture and the gate deselects nothing. Factory
  resolves the Issue, not this task: FCT-4's handoff item 2 says "resolve Issue `d6040ce8` when SEL-050 has
  landed". It stays open until the dispatcher merges this branch and factory transitions it.
  `seldon issue show d6040ce8` in this repository answered `Issue 'd6040ce8' not found`, so I could not read its
  current state from here, and I changed nothing about it.
- **The other intermittent named beside the Issue** is `union_merge` (ADDENDUM 01). It passed in this run. Its fix
  is still a separate task under `seldon/`, untouched here.
- **The live comparison is still red** (2026-11-26, 21.4 s): `assert '7a774aec1104...40fca2dceb9b0' ==
  'b81037645b27...045970f727009'`, the same values SEL-047 Part C recorded on 2026-11-25. The rebuild path does not
  reproduce the release the library serves today, and no gate asserts that now. The fixture shows seldon's path
  reproduces a release the kit builds today. Whether the live gap is in seldon's rebuild or in the library's
  checkpoint (for example, the AD-036-R30 known limit: 3 of 2,261 units differ under arm A's rule) is undiagnosed. It
  needs its own task, and filing one is the coordinator's decision (SEL-047 Part C: "This task files nothing").
  Re-run it with:
  `SELDON_PA002_LIVE=1 python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/test_pa002_release_resolve.py -q -p no:cacheprovider -k live`
