# RECALL-002R RESULT: recall is on in squiddy, arnold and ai-readiness-kg

**Date:** 2026-10-27. **Session:** Claude Code (headless), worktree `worktree-rippling-yawning-fox`, task ff3a4189.
**Addenda:** none (globbed `*RECALL-002R*ADDENDUM*.md`: no match). **Model calls:** zero. **Network:** none.

Recall used: none

The eight hits registration listed (SEL-005, QC-001, MODEL-001 and RECALL-001 RESULTs, AD-036-R5, squiddy R-196, Issue
f6c69653, arnold DN-002-R4) did not change the approach. The code read here did: `seldon/core/recall.py` `settings()`
and `repositories()`, and squiddy SQ-087's RESULT for which governed graphs exist.

## Premises

All four held: seldon.yaml carries `recall:` (line 346); squiddy, arnold and ai-readiness-kg each have a seldon.yaml.

## Part A: the three `recall:` blocks

| repository | commit (main, through its hooks) | served arm | siblings searched |
|---|---|---|---|
| squiddy | `b1bdaf8f` | on: squiddy, seldon, arnold `governed/` | seldon, arnold (already in `decisions.repositories`) |
| arnold | `bd951d9` | on: arnold, seldon, squiddy `governed/` | seldon, squiddy (squiddy **added** to `decisions.repositories`) |
| ai-readiness-kg | `acb6add6` | **off**, reason in the file | none (no `decisions:` block) |

Every value is seldon.yaml's own: `top_n` 8, `min_shared_terms` 3, `max_file_bytes` 2000000, `headline_chars` 120,
the two `result_globs`, the eleven `failure_terms`, `bm25` k1 1.2 b 0.75, `served.k` 20, `served.rrf_k` 60. Each
line's comment names the seldon.yaml key holding its reason.

The task said "copied by reference". The recall loader (`seldon/core/recall.py` `settings`) has no `ref:` form (only
`prior_art` and `dispatch.standing_band_ref` do), and the task allowed no code change (Spend: zero code, config
blocks only). So the values are copies, and each block says that a change starts in seldon.yaml. This follows squiddy's
`dispatch:` block ("values and reasons copied from ai-readiness-kg's block").

Three decisions the task did not anticipate. Each is recorded in the file it touches:

1. **arnold's `decisions.repositories` gains `squiddy: ../squiddy`.** `recall.repositories()` reads only that map, not
   `decisions.import`. Without the entry, arnold's recall would not search squiddy's history, although its evidence graph
   is a Squiddy graph (AD-033 R1, the `import: [squiddy]` line). The path is the one `import` already resolves
   (`decisions.settings` `setdefault`), so the register sees no change. Arnold has no `dispatch:` block, so the stations'
   environment premise, which also reads this map, is not reached.
2. **ai-readiness-kg's served arm is `enabled: false`.** It has no `governed/` graph, so AD-031-R1 is unmet there.
   SQ-087's "all three" were squiddy, seldon and arnold, not this repository, so the task's statement that "the arm is
   live" is wrong for it. Its one Squiddy graph, `graphs/ai-readiness`, is the domain corpus. `served()` keeps only
   hits that are RESULT candidates, so that graph could rank nothing. When a governed graph exists, setting
   `enabled: true` and `graphs` turns the arm on.
3. **ai-readiness-kg gets no `decisions:` block,** so its recall searches only its own history. That block turns on
   AD-033's register gates in that repository (`hooks.py`, `verify.py`, `desktop_commit.py` all key on
   `decisions.settings`), which is a separate adoption and outside this task's scope. Its recall ids read `blank:`
   because `recall.repositories()` falls back to `project.name`, and ai-readiness-kg's `project.name` is `blank`, a
   leftover from its scaffold. That name is not changed here because other code reads `project:`.

Other dirty files in those trees were not committed. Only `seldon.yaml` was staged: arnold's two modified files and
ai-readiness-kg's `seldon_events.jsonl` and `.githooks/commit-msg` are untouched.

## Part B: acceptance

`seldon cc register` has no `--dry-run`. The nearest read-only path is the register's own recall step, called
directly: `recall.settings`, then `recall.recall`, then `recall.render`, in the order `seldon/commands/cc.py` 1379-1506
calls them, without `record_listed` and without registering. Script: `docs/evidence/recall002r/check.py`. Full output:
`docs/evidence/recall002r/recall_check_output.txt`. Run with this worktree first on PYTHONPATH against the sibling
primaries after the commits above.

- **squiddy**, `cc_tasks/2026-10-24_SQ-087_..._index_rule.md`: `Recall: 8 hit(s) from the history of squiddy, seldon,
  arnold`. Results from both arms (SQ-018R, AD-030 ingest, SQ-010, DESK-002R, SEL-004, SQ-028R, RECALL-001); no
  served-arm note, so all three served graphs answered. 16.8 to 20.9 s.
- **arnold**, `cc_tasks/2026-10-22_workout-start-time.md`: `Recall: 8 hit(s) from the history of arnold, seldon,
  squiddy`. These include arnold's own register records (ADR-007, training-domain-vocabulary-B8, the cycle-reversal
  R2) beside seldon and squiddy RESULTs; no served-arm note. 12.2 s.
- **ai-readiness-kg**, `cc_tasks/2026-10-21_fcsm_concern_edges_and_sixteen_checks_one_pager.md`: `Recall: 8 hit(s)
  from the history of blank`, eight of its own RESULTs (G4 locators, DCAT brief, DCAT-005, report draft, ...). 0.6 s,
  lexical only.

None printed `not configured`.

Arnold's hits are weak on topic: the workout-start-time task shares generic terms with seldon infrastructure RESULTs.
This is the untuned `min_shared_terms: 3` that RECALL-001 already marks for its chart to move. It is not a defect of
this task.

## Closing

- c9a3cb9b (RECALL-002, no source file) superseded by ff3a4189 (`seldon task supersede`, 2026-10-27).
- **Not pushed.** Per the launch clause, this session does not merge or push. The three sibling commits sit on each
  repository's local `main`. The task file says DISP-004R's finish step pushes all four. If it does not, the operator's
  recipe, in a shell, any order:
  1. `git -C /Users/brock/GitHub/squiddy push origin main`
  2. `git -C /Users/brock/GitHub/arnold push origin main`
  3. `git -C /Users/brock/GitHub/ai-readiness-kg push origin main` (that branch was already 4 commits ahead of origin
     before this task. Those commits go out with it.)
