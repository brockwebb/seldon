# RESULT: Root-cause and fix `test_build_paper_unknown_xref_passthrough`

**Task:** `cc_tasks/2026-09-02_paper_build_xref_passthrough_failure.md`
**Date:** 2026-09-02
**Addenda:** none found (`cc_tasks/2026-09-02_paper_build_xref_passthrough_failure_ADDENDUM*.md` — no matches).

## 1. Reproduction on `main` HEAD (`f332e45`)

```
python -m dotenv -f .env run -- python -m pytest tests/test_paper_build.py::test_build_paper_unknown_xref_passthrough -x
```

Failing assertion: `tests/test_paper_build.py:620` — `assert exit_code == 0` → `assert 1 == 0`.

The build's own stdout (captured by pytest) shows the source of the exit 1. It is **not** the
xref resolver — the token passes through as designed — it is the Tier 0 copy-edit gate:

```
=== TIER 0: Copy Edit ===

CE-06 Double space in prose:
  01_intro.md:1: Double space in prose — "See {{figure:nonexistent}} for details."

TIER 0 SUMMARY: 1 violation across 1 file
...
Build: SUCCESS
```

The reported line contains no double space. `build.py` step 13 returns 1 whenever
`copyedit_violations` is non-empty ("CE violations are always blocking"), regardless of `skip_qc`.

## 2. Bisect

Range: `06c41d2` (last known green — the commit after the xref feature `59f6677`, which
introduced this test) → `86b039b`. Run in a throwaway worktree (the main tree carries an
uncommitted `seldon_events.jsonl` that a checkout would have clobbered), `bisect run` driven by
the single test under the dotenv form.

```
cf6cf0cf34ee72589e2d14ef6c009084201ab61c is the first bad commit
    feat(paper): Tier 0 copy-edit QC gate — seldon paper copyedit
```

Neither of the task's named candidates (`63228b0`, `86b039b`) is the culprit; the test has been
red since the Tier 0 gate landed (2026-04-20). `git bisect reset` run; `git worktree list` shows
only the main tree on `main`.

**Mechanism.** `check_CE_06` searched for `"  "` in the output of `qc._strip_skipped_regions`,
which (by its own docstring) replaces `{{...}}` reference tokens with *blank spaces of the same
length* to preserve line numbers. Every token that survives resolution — exactly the unknown-name
passthrough case — therefore reads as a run of spaces, and the single spaces on either side of
it complete a "double space". The Tier 0 test file never exercised a line containing a token, so
the interaction was invisible there.

## 3. Which side is wrong

Design record read: `docs/design/AD-016_paper_qc_severity_tiers.md` (severity tiers; CE = mechanical
defects, build-blocking) and the AD-018 B2 record carried in `59f6677`'s message ("Unknown names
pass through unchanged") plus `AD-018_document_structure_graph.md`. AD-016 makes *mechanical
formatting defects* blocking; a whitespace gap manufactured by the checker's own preprocessing is
not a defect in the prose. AD-018 B2 makes unknown-xref passthrough a non-fatal build outcome.
The two records are consistent with each other and with the test; only the check's
implementation disagrees.

**Verdict: the build's behavior (the CE-06 false positive) is wrong; the test's expectation
stands.** The test file was not modified.

## 4. Fix

`seldon/paper/copyedit.py`:
- new helper `_mask_reference_tokens(line)` — replaces each `{{...}}` token with a same-length run
  of a non-space sentinel (`\x00`), preserving columns without turning the token into whitespace;
- the `double_spaces` branch of `check_CE_06` now searches the raw line with tokens masked, and
  keeps `proc_line.strip()` as the guard that skips lines lying entirely inside fenced code or
  frontmatter (unchanged behavior for those regions).

Test written first, red, then green (`~/GitHub/CLAUDE.md` §5), in `tests/test_copyedit.py`:
- `test_CE_06_reference_token_is_not_a_double_space` — `See {{figure:nonexistent}} for details.`
  produces no double-space violation (failed before the fix: `AssertionError` at line 165);
- `test_CE_06_double_space_beside_token_still_flagged` — `See  {{figure:nonexistent}} for details.`
  is still flagged (positive control; the fix does not weaken the check).

No other test changes. AD-027 code paths untouched. Zero model calls. No project database written
(the suite's DB tests use the test database as they always do).

## 5. Full suite (dotenv form)

| | command | result |
|---|---|---|
| before (HEAD `f332e45`, throwaway worktree) | `python -m dotenv -f .env run -- python -m pytest tests/ -q` | **694 passed, 1 failed** (`test_build_paper_unknown_xref_passthrough`) |
| after (main tree with the fix) | same | **697 passed, 0 failed** |

The +3 is the one repaired test plus the two new regression tests.

## 6. CLAUDE.md invocation line

`CLAUDE.md` "Environment" paragraph still advertised `source .env && pytest tests/ -v`, the form
the snapshot RESULT showed silently skips every DB test under zsh. Replaced with the dotenv form
and a one-sentence note on why the shell form is not to be used.

## 7. Files

Modified: `seldon/paper/copyedit.py`, `tests/test_copyedit.py`, `CLAUDE.md`.
Created: `cc_tasks/2026-09-02_paper_build_xref_passthrough_failure_RESULT.md`.

Out of scope, noted only: `docs/design/guarded_incremental_change_cycle.md` is an untracked file
already present in the tree before this task; not touched.
