# RESULT: TRIAGE-001 open proposals triaged; `Moving:` line (2026-10-15)

**Task:** `686ce776`. **Population:** 20 `proposed` (none `accepted`). `1581c3ec` is `blocked`, so it is outside the population and was not touched.
**Result:** 4 closed (3 superseded, 1 withdrawn), 2 moved to arnold, 11 rewritten FUTURE (the 12th, `1c989081`, was already FUTURE), 4 active.

| id | first words | decision | evidence |
|---|---|---|---|
| 0abd073a | log_workout endurance detector false positive | rule 3 → arnold `06272bec` | Arnold's code; superseded here, new id in reason (no cross-database edge) |
| bd904e76 | Suunto bulk export + per-split import | rule 3 → arnold `ce03be52` | as above; arnold's event log is gitignored, tree untouched |
| 3454bf69 | Keshav five-Cs rubric for Molly intake | withdrawn | Molly mothballed (this task's own premise); no Molly repo under ~/GitHub |
| 63e151d5 | ADDENDUM to 6dad25b9 (edge cases) | superseded → `6dad25b9` (edge) | its parent's FUTURE text names it as required input |
| 7e862893 | outlined state gate for PaperSection | FUTURE | no `outlined` state in research.yaml; only SETUP-02 asks for the lock |
| 84c880a8 | build artifact tracking for AD-018 | FUTURE | AD-018 has no build-tracking decision; SETUP-05 leaves it to each project |
| 59d67aeb | codify academic bold usage | FUTURE | not in authoring_conventions.md |
| 6dad25b9 | source provenance tiers | FUTURE (+63e151d5) | authoring_conventions.md §1 has no tiers |
| 369fc223 | review.intent in seldon.yaml | FUTURE | field absent; "after ICSP and SFV ship" |
| 69494d5c | Manuscript TEVV provenance layer | FUTURE | its own priority: low, after SFV |
| 30746b6b | Naïve Reconstruct audit gate | FUTURE | no such persona in audit_pipeline.md |
| af389420 | namespaced ontology module | FUTURE | `ONTOLOGY_MASTER_DB` still a constant (config.py:14) |
| b8a8d85e | `seldon governed init` | FUTURE | partly done: arnold by hand copy (a893d36), per-project dirs; init + zero-ruling warning open |
| ace164ee | PA-001 governed-graph arm | FUTURE | waits on AD-031-R1 coverage of sibling repos |
| f4b2ffb4 | PA-001 library cold start 21.1 s | FUTURE | unaddressed; trigger is a seen timeout |
| 1c989081 | non-Anthropic providers | FUTURE (already) | unchanged |
| e60b17fe | SEL-003 Phase 1b | **active** | below |
| 814e95d7, 066e5b69 | artifact name uniqueness; `artifact list` names | **active** | below |
| fcc0ed89 | secrets out of claude_desktop_config.json | **active** | below |

**Active.**
- `e60b17fe`: the AD-033 §6 pre-registration is frozen, and AD-033-R7 keeps registration binding "advisory" until it runs. It is the one task with a source file, but the dispatcher refuses it (`no_header:Spend,Framework layer served`). It needs those headers and `**Parts:**` added in an addendum before it can launch.
- `814e95d7` / `066e5b69`: verified unfixed at HEAD. There is no `--allow-duplicate-name`, `artifact list` has no name output, and `superseded_by` is still ResearchTask-only (research.yaml:989). They are silent-twin defects with a known fix and no task file.
- `fcc0ed89`: verified today. The GitHub PAT and the Census key are still inline, and 9 entries carry the Neo4j password (key names read, values not). The gate is Brock's go and the token rotation, both his.

**Questions.**
1. Supersede across repositories writes no edge, because `superseded_by` cannot leave the database. Reading A: the id in the reason is enough. Reading B: add a cross-project reference type.

**Part B.** `seldon/core/moving.py` (new) holds the predicate and the count. `go` prints the line first in text form (which the MCP `seldon_go` uses) and as the first key of `--json`; `status` prints it first. The dispatcher's `_tasks` drops FUTURE rows, so pass counts, the log, `last_pass` and `status` exclude them. Only the registration commit still reads them. `evaluate` refuses FUTURE as `future` for any caller. The window is `status.closed_window_days` (default 7, rolling). `tests/test_moving.py`: 18 tests, fake driver; they were written after the code, not first.

**Line as printed** (`seldon status`, `seldon go`): `Moving: 1 in progress, 1 proposed with a source file; 12 future ideas; 19 closed this week.` The hand count by Cypher gives 1 / 1 / 12 / 19. `seldon dispatch status`: 4 open, 0 candidates.

**Checks.** Proposed tasks with no source file and no FUTURE prefix: `814e95d7 066e5b69 fcc0ed89`, all three named active. Every in-graph supersede has its edge (`63e151d5`→`6dad25b9`); the two cross-repo supersedes carry the new id in the reason. Every withdraw has its reason. Full suite, run detached and polled: **2539 passed, 1 failed** in 23:08 (`docs/evidence/triage001/full_suite.txt`). The failure was `test_go_json_output_has_expected_keys`, which pins `go --json`'s key set and did not yet list the new `moving` key. I added the key. I did not re-run the whole suite: `test_go.py` and `test_moving.py` re-run gives 55 passed. `seldon verify`: all checks pass after `make -C governed catalog` and `sweep`. Export hit DI-110 on the second sweep of the day, so the release was cut as `20261015_sweep_triage001`, then `governed sync` (2 documents created).
