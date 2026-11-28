# SEL-060 Part C: the selection's values, chosen on the replay

**Produced by:** `replay_repository` (`seldon/core/recall_audit.py`) over seldon's and factory's last thirty
dispatched tasks, once per variant, from a scratch driver in the session (each variant is a different
`recall.selection`, so its checkpoint key differs). Run 2026-11-27 before factory's OODA-025 launched, so factory's
window is FAC-40 to FAC-60 here and OODA-012 to OODA-025 in `replay.md`; seldon's window is the same. The variant
committed is the first row; `replay.md` is its final run.

"opened" is what the sessions opened of the new hits (in-sample, see `replay.md` section 1); old lists for the same
tasks: seldon 23 of 240, factory 20 of 240.

| variant | max_citing_share | max_file_hits | max_issue_hits | decision lexical | seldon hits, opened | factory hits, opened |
|---|---|---|---|---|---|---|
| **committed** | 0.30 | 1 | 0 | 4 | 233, 53 | 189, 21 |
| | 0.30 | 2 | 1 | 4 | 237, 50 | 197, 18 |
| | 0.10 | 2 | 1 | 4 | 234, 52 | 174, 19 |
| | 0.30 | 2 | 1 | 8 | 220, 48 | 188, 18 |
| | 0.30 | 0 | 0 | 8 | 174, 47 | 133, 18 |
| | 0.30 | 4 | 3 | 8 | 223, 42 | 206, 20 |
| first draft | 0.10 | 4 | 3 | 8 | 214, 43 | 193, 15 |

Before the citation-share rule existed (a run not in the table), every cited note was expanded to the tasks that
changed it, so every seldon task citing AD-037 got
QC-001's RESULT and every one citing AD-038 got FRICTION-001's; that is what the citation-share rule removed
(`DN-005` is in 47% of seldon's task files, `AD-037-R6` in 33%). At four file-history and three Issue hits, stage 2
handed seldon 63 hits opened once and factory 93 opened 4 times, and stage 3 handed 71 opened twice.

Consulted RESULTs held by the list did not move between variants (seldon 13 of 51, factory 3 of 74; old 7 and 3).
