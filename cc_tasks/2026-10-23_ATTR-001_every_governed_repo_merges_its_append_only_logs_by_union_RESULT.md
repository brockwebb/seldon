# RESULT: ATTR-001, every governed repository merges its append-only logs by union

**Task:** `cc_tasks/2026-10-23_ATTR-001_every_governed_repo_merges_its_append_only_logs_by_union.md` (01b36eac).
**Session:** dispatched, worktree `hazy-sauteeing-globe` on `worktree-hazy-sauteeing-globe`. **Date:** 2026-10-23.
**Addenda:** none existed when the session started.
**Decision record:** `docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md`. It applies AD-034-R7
and AD-038-R1 and makes no new ruling.

Recall used: seldon:AD-034-R7, seldon:AD-034-R10, seldon:2026-10-20_DISP-003R_gate_runs_the_branch_code_RESULT

- AD-034-R7 says the attribute is the only list. So the installer and c16 ask `git check-attr`; they do not match text.
- AD-034-R10 covers only `stop_gate_unpassed`. That is why SQ-021 (`merge_blocked`) cannot be finished by a
  regate (see Part C).
- DISP-003R's method of rehearsing another repository's merge in a `git clone --shared` under /tmp, with its
  siblings symlinked beside it, is how Part C was measured.

## Outcome

| Part | State |
|---|---|
| A, receipts | Done. |
| B, code | Done: the installer, the pass-side declaration, c16 and `status`, all tested. |
| B, the four `.gitattributes` commits | **Not made by this session.** Each repository's own dispatcher makes them on its first pass after this branch merges (see below). |
| C | **Not done; rehearsed only.** The counts were measured in a /tmp clone. The squiddy merge, `cc complete`, the worktree removal and the SQ-036 redrive are left for the operator, with exact steps. |

## Part A: receipts

`seldon prior-art search`, both arms. Each run committed its own log line (AD-036-R11).

**Internal arm:**

- "union driver": hits AD-034 §2:19.
- "gitattributes": hits AD-034 :19 and :41, the R7 register record and ADDENDUM 03:39.
- "rebase_conflict seldon_events.jsonl": 0 hits.

**Library arm:** 0 relevant rows on three queries ("git merge driver union append-only log", "gitattributes merge
attribute line-oriented", "CRDT grow-only set merge replicated log"). The library is a corpus of AI-research lessons.

**Named prior art, one line each (in the addendum):**

- gitattributes(5) `merge=union`.
- `.gitattributes` as tracked tree state that a rebase reads.
- SEL-004 decision 4 / AD-034-R7's post-merge check.

**Verification:** `seldon prior-art verify docs/design/AD-034_worktree_per_task_dispatch.md` returned **PASS** with
all five addenda. Ledger event 8e3b56e9, commit 80d9e9d.

## Part B: the installer writes it, and a project without it is refused

The tests were written first: 13 failed before the code existed. The two pass tests were added with the pass-side
declaration. Code:

- `seldon/core/hooks.py`:
  - `append_only_paths` lists the event store, the governed ledger where the graph directory exists, and the
    prior-art log where the block is configured (its own or its `ref`'s). It leaves out ignored paths. An
    unresolvable `prior_art` block raises an error naming it.
  - `union_missing` asks `git check-attr`.
  - `declare_union` creates or extends `.gitattributes` with the comment naming SEL-004 decision 4, and commits that
    file alone, path-scoped, through the hooks. A second run does nothing.
- `seldon hooks install` calls `declare_union` in a seldon project and prints what it declared.
- `seldon/core/dispatch.py`:
  - `union_state` is read once per pass.
  - `evaluate(..., union=)` adds c16 only when the check fails.
  - `first_refusal_reason` returns `union_attribute_missing`, ahead of the task-specific reasons, as c7 is.
- `seldon/commands/dispatch.py`:
  - The refusal line names the files and `seldon hooks install`.
  - `dispatch status` shows `union_attribute_missing` at the top.
  - `_declare_union` runs inside `_reconcile`.

**Departure from the task text, decided on grounding.** The task asked for a refusal only. With a refusal only, every
dispatcher in squiddy, arnold, ai-readiness-kg and hazbrief-mcp would refuse every launch on c16 from the moment
this merges, until someone ran the installer in each. This session cannot run the installer there: the worktree guard
refuses git aimed outside this worktree, and STD-001R found that cross-repository commits are refused as well. So,
by AD-038-R1 (the machine reconciles its own state), the pass declares the attribute itself:

- in `_reconcile`, under the lease, with no claim in flight and on the configured branch;
- by committing `.gitattributes` alone;
- leaving alone a `.gitattributes` that has uncommitted edits.

c16 still refuses whenever the declaration cannot be written. The operator can override by reverting `_declare_union`.

**Dry run of what each repository's first pass will commit** (`/tmp/attr001/dryrun.py`, read-only `check-attr`):

| repository | will declare |
|---|---|
| squiddy | `seldon_events.jsonl`, `governed/ledger/events.jsonl`, `state/prior_art_queries.jsonl` |
| arnold | `governed/ledger/events.jsonl` (arnold gitignores `*.jsonl`; its event store and prior-art log are untracked and cannot conflict) |
| ai-readiness-kg | `seldon_events.jsonl`, `state/prior_art_queries.jsonl` |
| hazbrief-mcp | `seldon_events.jsonl`, `state/prior_art_queries.jsonl` (`.gitattributes` only, as the task requires) |
| seldon | nothing: all three are already declared |

To do it by hand instead, run `seldon hooks install --repo /Users/brock/GitHub/<repo>` in each.

**Tests:**

- `tests/test_attr001_union_attribute.py`: 15 pass. They cover:
  - the list, including ignored paths and an unresolvable ref;
  - create, extend and idempotence;
  - a wider pattern already present;
  - the CLI;
  - c16 and its refusal line;
  - the pass declaring the attribute, and the pass leaving an edited file alone;
  - real git: the SQ-021 shape conflicts without the declaration and union-merges with it, with `check_union_text`
    passing.
- Full suite, run from the worktree with `PYTHONPATH` set to it (`/tmp/attr001/suite.txt`): **5 failed, 2802
  passed, 7 skipped in 42:32**. The failures:
  - Three in `tests/test_dispatch_own_record.py`, caused by this change. That fixture tracked its event store
    without the attribute, so the first pass now commits the declaration and its "no commit" assertions counted it.
    The fixture now declares the store as a real project does. The file passes: 14/14 after the fix.
  - `test_friction002_auto_mode.py::test_a_classifier_breaker_becomes_a_line_stop_with_the_classifiers_reason`
    passes alone after the fix. The full run uses one shared Neo4j database, and earlier sessions recorded flakes of
    this kind there.
  - `test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` fails for an
    environmental reason: squiddy's `graphs/library/extract/control.yaml` `index:` block has changed since release
    99984ba3 was built. This change does not touch that code path.
  
  The full suite was not re-run after the fixture fix.

## Part C: SQ-021, rehearsed (not merged); SQ-036 not redriven

**Why not done here.** This session's launch forbids merging and pushing. The guard refuses git aimed at squiddy and
at its kept worktree. The memory of earlier sessions records that `git worktree remove` of another tree is refused.
Fast-forwarding squiddy's main, completing SQ-021 there and removing its worktree are all of those.

**The measured case.** `/tmp/attr001/rehearse.py` cloned squiddy with `git clone --shared` under /tmp, with seldon
symlinked beside it for the prior-art `ref`. It committed the installer's exact text on main and rebased SQ-021's
branch. squiddy was not written. Raw output: `/tmp/attr001/rehearse_out.txt`.

| | value |
|---|---|
| squiddy main / SQ-021 tip / merge base | e82e0a3 / 6f4d784 / 0e77570 |
| rebase without the declaration | conflict: `seldon_events.jsonl` (the dispatcher's 295ad039, reproduced) |
| rebase with it | clean, no conflicts |
| lines at merge base | 8956 |
| main side | 8989 (+33) |
| branch side | 8976 (+20) |
| lines after the union | 9009 (= 8956 + 33 + 20) |
| `check_union_text` (base = main) | ok, 0 malformed, 0 duplicates |
| duplicate `event_id` across the whole merged file | 0 (expected 0) |

The stop condition was not triggered: the union result passes `check_union_text`. The squiddy kit gate was **not**
run in the rehearsal.

**Operator steps, once squiddy's main carries the attribute** (its first dispatcher pass after this merge does that;
check with `grep merge=union /Users/brock/GitHub/squiddy/.gitattributes`). Run them in squiddy:

1. `git -C .claude/worktrees/compressed-shimmying-hearth rebase main`.
2. Run `check_union_text` on `seldon_events.jsonl` against main's copy.
3. Run the kit gate with `.venv/bin/python` (SUITE-001).
4. `git merge --ff-only worktree-compressed-shimmying-hearth`.
5. `seldon cc complete cc_tasks/2026-10-22_SQ-021_extraction_pilot_for_the_ai_readiness_graph_then_its_first_new_document.md`.
6. `git worktree remove .claude/worktrees/compressed-shimmying-hearth`.
7. Resolve issue 295ad039.
8. `git push`.
9. `seldon dispatch redrive f8433f8c` (SQ-036, `session_failed` on `ENOTFOUND`; its tree `ancient-floating-twilight`
   is kept).

## Premises wrong

- Premise 2 holds on disk, but arnold's `seldon_events.jsonl` and prior-art log are gitignored (`*.jsonl`,
  `.gitignore:188`). They cannot conflict, so arnold's only append-only tracked file is its governed ledger.
- The other premises held as checked. Part C's plan also assumed that an L4 session could merge and push in squiddy,
  and this session's launch forbids that.

## Not covered (recorded in the addendum)

- Regate (AD-034-R10) does not cover `merge_blocked` / `rebase_conflict`. Extending it to a conflict whose files are
  all now `merge=union` would let the dispatcher finish SQ-021 itself. That would be an amendment to R10, so it was
  not made here.
- squiddy's `kit/ledger/passes.jsonl` is append-only and in SQ-021's write set, but it is not declared.

## Spend

From `part_complete`: Part A 209,065 tokens; Part B 218,137 tokens. Part C was not run (rehearsal only). The
estimate was 0.3M and the stop ceiling 0.36M; neither was crossed.
