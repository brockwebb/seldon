# SEL-060 Part C: the old and the new selection replayed on seldon's and factory's last thirty dispatched tasks

**Produced by:** `seldon qc recall-replay --repo seldon --repo factory --last 30 --checkpoint
docs/evidence/sel060/replay_rows.jsonl` (code: `seldon/core/recall_audit.py` `replay_repository`), run 2026-11-27
from the task's worktree with seldon.yaml's `recall.selection` as committed in `9ced980`. One row per task in
`replay_rows.jsonl`. Zero model calls; about a minute for both repositories.

## 1. What was replayed

- **Tasks:** each repository's last thirty dispatched sessions with a task file on disk, by first launch (seldon
  SEL-029 to SEL-060; factory OODA-012 to OODA-025, of which fourteen are OODA check-ins).
- **Old:** seldon: the `recall_listed` record each task got at registration (30 of 30), what the session was
  actually handed. factory has no `recall:` block, so RECALL-001's lexical selection was replayed with seldon's
  values and the served arm off.
- **New:** `recall.selection` (`mode: touch`), as of each task's launch: only a RESULT whose file had landed in the
  checkout before the launch is a candidate, and the commit history is read up to the launch day.
- **Opened:** the session's own log names the hit (the Part A rules). For the new hits this is in-sample: the
  session was never handed them, so "opened" means it went and read that history unprompted.
- **Consulted:** every RESULT file name the session's tool calls named, handed or not: the history it actually used.

## 2. Results

| | seldon old | seldon new | factory old | factory new |
|---|---|---|---|---|
| hits handed (30 tasks) | 240 | 233 | 240 | 190 |
| hits per task | 8.0 | 7.8 | 8.0 | 6.3 |
| tasks with no hit | 0 | 0 | 0 | 2 |
| hits the session opened | 23 (9.6%) | 53 (22.7%) | 21 (8.8%) | 21 (11.1%) |
| RESULTs consulted that the list held (of 54 / 76) | 7 | 13 | 3 | 3 |

Per task, the new list held more of what seldon's session opened in 19 tasks and less in none. In factory, 7 more,
8 fewer. In each of the 8, what the old list had and the new did not was the RESULT of the previous task of the
same kind, which the session opened and the task file does not cite: OODA-011 for OODA-012, OODA-018 for OODA-019,
FAC-43 for FAC-47 (the same title), FAC-41 for FAC-48. The lexical arm found them by the shared title; the new
selection hands no lexical RESULT (Part A: 2.2% opened). A stage for "the latest RESULT of a task with the same
title" is the evident next candidate, for the week's re-run to weigh; it is not built here.

By stage (new hits, opened):

| stage | seldon | factory |
|---|---|---|
| 1. the task cites it | 124, 38 | 124, 16 |
| 2. an earlier task changed the same file | 29, 1 | 24, 0 |
| 4. a recent dead end of the same kind | 8, 1 | 6, 0 |
| 5. lexical above the kind's threshold (Issues, decisions) | 72, 13 | 36, 5 |

Stage 3 (Issues naming the files) is off (`max_issue_hits: 0`); `replay_sweep.md` has why.

## 3. Reading

- The new selection is better in seldon by every count and level in factory: the same opens from 50 fewer hits.
- **Stage 2, the coordinator's own rule, did not earn its slot on this measure:** one open in 53 file-history hits.
  The measure is biased against it (a session cannot open history it was not told exists, and Part A's rows show a
  handed hit is opened far more often than an unhanded one), so it is kept at one hit per task rather than removed,
  and the week's re-run (filed with this task) reads it on hits sessions were actually handed. If a handed
  file-history hit is opened less often than Part A's uncited RESULT (2.2%), `max_file_hits` goes to 0.
- Consulted history the list held doubled in seldon (7 to 13 of 54) and stayed at 3 of 76 in factory: most of what
  factory sessions read is the current day's OODA RESULTs, written after the task was registered.

## 4. Limits

- Thirty tasks per repository; no interval is claimed. seldon's old list is the real one, factory's is a replay.
- A RESULT edited after a task launched is excluded from that task's candidates (its modification time is later),
  so the replay can miss a hit the task would have got; it cannot find one that did not yet exist.
- Opening is a lower bound on looking (Part A).
