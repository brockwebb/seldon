# PRUNE-001 Part A: seldon, open Issues resolved (2026-10-17)

Run record: `docs/evidence/prune001/part_a_run.json` (`seldon prune run`, rules in seldon.yaml `prune:`, code `seldon/core/prune.py`). Before-state: `before_dry_run.json`. Database `seldon-seldon-self`.

**Counts.** Open Issues: 9 before the hand pass, 8 after. Proposed tasks 24; FUTURE proposals 12; stale FUTURE (60 days): 7 before, 0 after.

| issue | rule | commit (the reason) | lead |
|---|---|---|---|
| `25da4d06` | hand (outside the rules) | `02de85f` | pin now names squiddy 627da34; R-186 row: uncataloged 13 -> 0 |

`fixed_marker`: the commit is the branch head when the Issue was filed; an Issue whose own lead says FIXED was filed after its fix.

**Stale FUTURE proposals (rule 2), by hand.** Seven proposed FUTURE tasks were older than 60 days, none with an edge from an open task. All seven were re-dated (`seldon prune redate`), none withdrawn: each trigger is a paper or audit event, and the paper projects moved this week (icsp_notebook 2026-10-14, book_responsible_ai 2026-10-11). Each reason is on the task as `redate_reason`: `7e862893`, `84c880a8`, `59d67aeb`, `6dad25b9`, `369fc223`, `69494d5c`, `30746b6b`.
