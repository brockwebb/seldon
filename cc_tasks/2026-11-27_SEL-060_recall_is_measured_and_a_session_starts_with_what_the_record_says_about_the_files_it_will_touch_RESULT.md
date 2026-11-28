# RESULT: SEL-060, recall is measured, and a session starts with what the record says it has reason to open

**Date:** 2026-11-27. **Session:** Claude Code (headless), worktree `worktree-lively-weaving-cascade`, task 4bf74fa6.
**Addenda:** none (globbed `*SEL-060*ADDENDUM*` and, as the task says, `*SEL-059*ADDENDUM*`: no match).
**Model calls:** zero in the code built; the measurement and the replay read files only. **Network:** none.
**Commits:** `498ee79` (Part A), `ae26b98` and `9ced980` (Part B), `ee85dee` (Part C evidence), `07b4c8c`/`5dac929`
(SEL-061 filed), this RESULT and the returns after them. Not merged, not completed: the dispatcher's.

Recall used: seldon:2026-10-17_RECALL-001_registration_retrieves_the_repos_own_history_RESULT, seldon:2026-10-27_RECALL-002R_recall_turned_on_in_squiddy_arnold_and_ai_readiness_kg_RESULT

Both were cited by the task and opened. RECALL-001's RESULT and `recall.py` gave the design kept here; RECALL-002R's
"the loader has no `ref:` form, so the values are copies" is what AD-031-R6 answers. SEL-055's RESULT, squiddy
R-266, and the other hits were not opened. R-266 came in on eight shared generic words, which is the kind of hit
Part A counts.

## Part A: is recall used

`seldon qc recall-audit` (new, `seldon/core/recall_audit.py`) reads every registered repository's dispatch logs. The
repositories come from factory's `portfolio.repositories`. Evidence: `docs/evidence/sel060/part_a.md` and
`part_a_tables.md`.

**Baseline: of 2,264 hits handed to 286 sessions in four repositories, 328 (14.5%) were ever opened. RESULTs named
376 (16.6%) as used, and 136 of those were never opened.**

| hit | handed | opened | used |
|---|---|---|---|
| RESULT the task file cites | 354 | 43.8% | 52.0% |
| decision record the task file cites | 38 | 63.2% | 68.4% |
| RESULT the task file does not cite | 1,518 | 2.2% | 3.8% |
| decision record it does not cite | 150 | 10.0% | 16.0% |
| Issue | 184 | 53.8% | 44.6% |

- **By repository, used:** hazbrief-mcp 21.7%, seldon 12.1%, squiddy 9.1%, ai-readiness-kg 2.3%.
- **The served arm:** opened 2 of its 490 hits.
- **Repositories handed nothing:** factory, critical-thinking-ai and aacps-ai-policy (101 sessions) have no
  `recall:` block. arnold has no dispatch logs. icsp_notebook has neither.
- **Two earlier counts were wrong and are not used** (part_a.md, "How it was counted"):
  - any glob counted as an open, giving 91.6% opened;
  - Write inputs counted as reads, giving 20.0%.

## Part B: hits a session has reason to open

- **The note:** AD-031 ADDENDUM 01, rulings AD-031-R4 to R7. `seldon prior-art verify` passes (28 receipts). The
  register records are pending under `docs/decisions/register/pending/`.
- **The selection** (`recall.selection.mode: touch`, `seldon/core/recall.py` `_touch_hits`) runs these stages in
  order. Each hit carries a `why:` line under it.
  1. Cited: RESULTs, dead ends and records the task cites. A citation carried by more than 30% of the
     repository's task files belongs to the template and is not a reason (`DN-005`, `AD-037-R6`).
  2. Files: the RESULT of the earlier task whose commits changed a file the task names or a note it cites. At most
     1 per task. A file that more than 12 tasks changed does not count.
  3. Issues that name those files: off (0).
  4. A kept or superseded task of the same prefix in the last 30 days.
  5. Lexical hits, only for Issues (8 or more shared terms) and decisions (4 or more). Lexical RESULTs are off
     (`null`) on Part A's 2.2%.
  - The served arm is not run.
  - A short list or an empty one is allowed.
- **This task under its own new selection:** 8 hits, each with its why.
  - Cited: RECALL-001, RECALL-002R, SEL-055 and SEL-059.
  - On files: FRICTION-001, because it changed AD-038's base note.
  - Lexical: three decision records at 6 to 8 shared terms, squiddy R-266 among them. The shared terms are generic
    ("about, measured, record"), so the decision threshold of 4 is one of the numbers SEL-061 reads.
  - The note says `DN-005` is not a reason.
  - With no `selection:` block, a repository keeps RECALL-001's selection unchanged.
- **`recall: {ref: <file>#recall}`** is laid over by the project's own keys. `seldon project new` writes
  `recall: {ref: ../seldon/seldon.yaml#recall, served: {enabled: false, ...}}` for a repository with no block, and
  skips when the kit has none (`recall_step`).
- **Tests:** `tests/test_sel060_recall_selection.py` (16) and `tests/test_sel060_recall_audit.py` (13). They include
  a SIGKILL-and-resume test of the replay's checkpoint (constitution section 15.8).

## Part C: measured on replays, and returned

`seldon qc recall-replay --repo seldon --repo factory --last 30`. Evidence: `docs/evidence/sel060/replay.md`,
`replay_rows.jsonl` and `replay_sweep.md`.

| | seldon old | seldon new | factory old (replayed) | factory new |
|---|---|---|---|---|
| hits (30 tasks) | 240 | 233 | 240 | 190 |
| opened by the session | 23 | 53 | 21 | 21 |
| RESULTs it consulted that the list held | 7 of 54 | 13 of 54 | 3 of 76 | 3 of 76 |

- **seldon:** the new list held more of what the session opened in 19 tasks and less in none.
- **factory:** 7 more, 8 fewer. All 8 losses were the previous task of the same kind (OODA-011 for OODA-012, FAC-43
  for FAC-47), which only the lexical arm had found.
- **The coordinator's file-history rule was opened once in 53 hits.** This measure cannot credit history that the
  session was never told existed, so the rule is kept at one hit per task. SEL-061 (filed, task 2098b773, launches
  on or after 2026-12-05) re-counts Part A on hits that sessions were actually handed. It sets `max_file_hits` to 0
  if those hits are opened less often than 2.2%, and weighs a same-title stage.

### Decisions taken on the grounding (L4), for the operator to override

1. The coordinator's order of stages stands. Its numbers were moved by Part A and the replay: lexical RESULTs are
   off, Issues come by name only lexically, and the file stage gets one slot.
2. The recall note the task names did not exist: RECALL-001 wrote only the module's docstring. AD-031, the
   retrieval note RECALL-001 extends, takes the addendum.
3. A repository with a copied block keeps the lexical selection until it moves to the reference. This applies to
   squiddy, hazbrief-mcp, arnold and ai-readiness-kg. Only hazbrief is returned below because the task names four
   consumers. squiddy, arnold and ai-readiness-kg are open: their blocks are RECALL-002R's copies.
4. **Erratum in the task file.** Its text says SEL-059 in three places: the addendum glob, the RESULT name in Part
   C's check, and the title. That was its number before allocation; SEL-059 is a different task (squiddy SQ-155).
   - The station reads the check from the primary's task file, so the check would fail as written and the branch
     would not merge.
   - A pointer file at the name the check reads holds a `## For the consumer` heading that sends the reader here.
   - This RESULT is the task's.

### The suite

- **Full suite at `9ced980` plus the evidence commits** (`python -m dotenv -f .env run -- python -m pytest tests/
  -n 6`): 3,722 passed, 8 skipped and 1 failed, in 46 minutes, EXIT=1.
- **The failure:** `tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid` (`merge_blocked`
  with `main_kept_moving` after 3 attempts). It is the load-sensitive failure SEL-049 recorded. It touches nothing
  this task changed, and it passes alone (1 passed, 38 s).

### Not done or not verified

- The register records are pending. The dispatcher numbers them at the merge.
- Registration from this worktree ran main's installed code, so SEL-061's printed Recall list is RECALL-001's
  lexical list. The new selection reaches registrations after the merge.
- TDD order: the selection was written before its tests, against Part A's numbers, and the tests were written after.
  The tests fail on main, where the functions do not exist.

## Returns filed

Each return was filed with `seldon cc return <this task> --to <repo> --answers <repo>:<task>` and registered in that
repository, which committed it.

| repository | return | task id | answers (named so it can be filed) |
|---|---|---|---|
| factory | FAC-66 | a7d2ec72 | FAC-41 |
| critical-thinking-ai | CTAI-021 | f5cef002 | CTAI-010 |
| hazbrief-mcp | HB-244 | 0677488f | HB-73 |
| aacps-ai-policy | AP-08 | 55ab8037 | AP-03 |

Each return's template line says that the named task "was filed into seldon", which is false. Its section's first
sentence says so. Each return carries a step 0 that checks for the merged code by function name.

## For the consumer

Each section below is a return task, filed with `seldon cc return`. None of the four consumers has to write code.
Each one gets the new recall by REFERENCE to seldon's block, so a later change to a number in seldon reaches them
without another copy.

### For factory

**Spend:** est. 0.05M tokens. Basis: one convergent command and one commit; no model calls of its own.
**Network:** none beyond git.

This return answers seldon SEL-060, and FAC-41 is named only so it can be filed: nothing was filed into seldon.
SEL-060 counted, from every registered repository's dispatch logs, which recall hits sessions opened. factory's 82
sessions got none, because factory's seldon.yaml has no `recall:` block. A replay of factory's last thirty tasks
under the new selection is in seldon's `docs/evidence/sel060/replay.md`.

0. Check that SEL-060 is on seldon main: `grep -q 'def recall_step' ../seldon/seldon/core/project_new.py`. If the
   check fails, stop and report "SEL-060 not merged". Do not use a commit sha: the dispatcher rebases before it
   merges.
1. From factory's primary checkout, run `seldon project new .`. The `recall` step writes
   `recall: {ref: ../seldon/seldon.yaml#recall, served: {enabled: false, k: 20, rrf_k: 60, graphs: {}}}`. If any
   other step says `changed`, report it.
2. Confirm it: `python -c "import yaml; from seldon.core import recall as R; print(R.settings(yaml.safe_load(open('seldon.yaml')), '.').selection['mode'])"`
   prints `touch`.
3. Commit through the hooks. The next registration prints `Recall:` with a `why:` line under each hit, or
   `Recall: none`.

### For critical-thinking-ai

**Spend:** est. 0.05M tokens. Basis: one convergent command and one commit; no model calls of its own.
**Network:** none beyond git.

This return answers seldon SEL-060, and CTAI-010 is named only so it can be filed: nothing was filed into seldon.
CTAI-010's RESULT says it was given no recall hits, and registration here prints
`Recall: not configured (seldon.yaml has no recall: block)`. SEL-060 makes the block one reference to seldon's.

0. Check that SEL-060 is on seldon main: `grep -q 'def recall_step' ../seldon/seldon/core/project_new.py`. If the
   check fails, stop and report "SEL-060 not merged".
1. From the primary checkout, run `seldon project new .`. Its `recall` step writes the reference block. If any other
   step says `changed`, report it.
2. Confirm it: the step 2 command in factory's section prints `touch`.
3. Commit through the hooks.

### For hazbrief-mcp

**Spend:** est. 0.08M tokens. Basis: one block replaced and one commit; no model calls of its own.
**Network:** none beyond git.

This return answers seldon SEL-060, and HB-73 is named only so it can be filed: nothing was filed into seldon. HB-73
ADDENDUM-00 copied seldon's `recall:` block by value, because the loader had no `ref:` form. It has one now
(AD-031-R6).

What SEL-060 counted for hazbrief:

| measure | hazbrief-mcp | the four repositories |
|---|---|---|
| hits handed | 1,288 | 2,264 |
| hits used | 21.7% | 16.6% |
| hits opened | 18.4% | 14.5% |

Most of hazbrief's used hits are predecessors its tasks cite by code. The new selection hands those first, and it
hands no RESULT on shared words alone.

0. Check that SEL-060 is on seldon main: `grep -q 'def recall_step' ../seldon/seldon/core/project_new.py`. If the
   check fails, stop and report "SEL-060 not merged".
1. Replace the `recall:` block (lines 358 to the end of its `served:` block in seldon.yaml as of 2026-11-27) with:
   `recall: {ref: ../seldon/seldon.yaml#recall, served: {enabled: false, k: 20, rrf_k: 60, graphs: {}}}`. Keep the
   reason the served arm is off (its HB-73 ADDENDUM-00 item 1 comment). If you would rather run
   `seldon project new .`, delete the block first: the step leaves an existing block alone.
2. Confirm it: the step 2 command in factory's section prints `touch`.
3. Commit through the hooks.

### For aacps-ai-policy

**Spend:** est. 0.05M tokens. Basis: one convergent command and one commit; no model calls of its own.
**Network:** none beyond git.

This return answers seldon SEL-060, and AP-03 is named only so it can be filed: nothing was filed into seldon. AP-03
brought this project to the factory's spec with `seldon project new`. That command now also writes the `recall:`
block, which aacps lacks: its 5 dispatched sessions got no recall hits.

0. Check that SEL-060 is on seldon main: `grep -q 'def recall_step' ../seldon/seldon/core/project_new.py`. If the
   check fails, stop and report "SEL-060 not merged".
1. From the primary checkout, run `seldon project new .`. If any step other than `recall` says `changed`, report it.
2. Confirm it: the step 2 command in factory's section prints `touch`.
3. Commit through the hooks.
