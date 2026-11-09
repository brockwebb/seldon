# RESULT: SEL-033, requirements and decisions live in the graph, the RTM and the requirements table are projections of it, and a project without a decision register is told so

**Task:** `cc_tasks/2026-11-09_SEL-033_requirements_and_decisions_live_in_the_graph_and_the_rtm_is_a_projection.md`
(0a8a6776). **Answers:** hazbrief-mcp filings SEL-031 and SEL-032, together. **Branch:** `worktree-zesty-cuddling-rain`
(merged by the dispatcher). **Design note:** `docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md`.

Recall used: seldon:AD-033-R1, seldon:2026-11-01_SEL-021_review_findings_are_issues_traced_to_fix_test_and_decision_RESULT

(AD-033-R1 already makes the register every task-registering repository's, which turned SEL-031's "is it optional"
into "nothing reads it", and set the warn-not-fail line of AD-033-R13. SEL-021's test-node `Script` is the target the
importer reuses for `verified_by`, with its test-reference grammar.)

## Outcome

All six Parts done. hazbrief-mcp's requirements are graph content: 214 `SRS_Requirement` nodes (149 from
`docs/VIEW_REQUIREMENTS.md`, 65 from `docs/REQUIREMENTS_TRACE.md`) with 410 trace edges, and its three files are
projections rendered from the graph and committed by `seldon docs generate requirements|rtm`. Every one of the 214 rows
in 33 tables rendered byte-identical to the hand-kept row, and the counts sentence rendered from the graph equals the
hand one (149 rows: 111 satisfied, 24 open, 11 changed, 3 withdrawn; 31 "none yet"; 4 not yet specified), so the
four-place ratchet is retired with no change to what a reader sees. hazbrief's own `tests/test_view_requirements.py`
passes on the rendered files (9 passed). The graph now answers SEL-032's three questions directly: which requirements
a test verifies (17 by `tests/test_hb131_panels.py`), which a decision constrains (`hazbrief-mcp:HBD-006`: S3-7 to
S3-10), and how many are unverified (49).

Two things not in the task were found and handled. (1) hazbrief's own HB-144 was running when Part D began and was
editing the same two files (it declared hazbrief's register and added a `Decision` column to the RTM), so Part D waited
for its merge and the importer learned the `Decision` column (`derived_from` to each register record; all 73 resolved).
(2) HB-144's merge numbered none of its 337 pending register records: the dispatcher's merge step read the config it
loaded before the fast-forward, which had no register. That is a seldon defect on SEL-031's own "register after the
fact" route; it is fixed here (`dispatch_worktree._config_at`, test first), and hazbrief's records were numbered on its
primary (`56bfb6f9`, `seldon decision check`: clean) and projected (995 `Decision` nodes), HB-144 RESULT's recipe.

One ruling was amended before numbering, because the full suite caught it: AD-013-R1 first let a requirement derive
from a governed `Document`, which would also have admitted `DataFile -> Document` against AD-030 section 4's closed edge
set. Document is out; the note, its pending record and the tests changed together.

## Part A: the design note and the rulings

- `docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md`; `seldon prior-art verify` **PASS** before any
  code (sha256 e9e17708e413, verdict event `100bd49b49fd48f5a3a508e127176a95`), and again on the amended note (sha256
  ea5d03a16db8, event `41027050351d4525acd9777f2c0e1b54`), both in the governed ledger.
- Prior art received: ISO/IEC/IEEE 29148 (attributes, bidirectional trace), ReqIF 1.2 (an object with typed attributes
  and typed relations; a document is a hierarchy over objects), SysML v2 (satisfy, verify, derive), IBM DOORS (a module
  is a view, the document is generated), Gotel and Finkelstein 1994 (source traceability fails when the source is not a
  link), Cleland-Huang et al. (hand-kept trace links decay), Cog (generated regions in hand-written files). Five
  internal and two library searches, receipts in the note. The library's one relevant row is the operator's own ANTS
  repository (`brockwebb/ai-native-traceability-system`, the `export_rtm` the task names).
- Rulings, register records pending (numbered at merge, AD-033-R12): **AD-013-R1** (a requirement is a graph
  artifact; `derived_from` its source, `verified_by` a test, `satisfies` from what meets it; `verified` needs a test),
  **AD-013-R2** (the table and the RTM are projections rendered into marker blocks, revision-stamped, committed; a
  markdown table is a load source, never the truth), **AD-013-R3** (`docs check` and `verify` report unverified
  requirements and stale projections, advisory), **AD-033-R13** (init, go and verify report a missing register;
  `project new` declares one).
- One departure from the task text, recorded in R1: the task said `satisfies` to "the ResearchTask or note the set-by
  names". A note does not satisfy a requirement; it is its source. `Set by` becomes `derived_from` (29148's source,
  SysML's derive); `satisfies` comes from the task a status names (`satisfied: HB-131R`).

## Part B: the load (`seldon req import`, `seldon req add`, `seldon req list`)

- `seldon/core/requirements.py`, `seldon/commands/req.py`. A pipe table whose header names an id column and a
  statement column is a requirements table; a `Key | File` table is the key map for `Set by`. Header names are
  configurable (`requirements.columns`, `--id-column` and the other `--*-column` options).
- Per row: the node, idempotent on `requirement_id` (a second import of an unchanged file writes 0 events, measured on
  hazbrief's 149 rows); `derived_from` to each `Set by` key's artifact (through the key map to a task's `source_file` or
  a Document's path, else a task name, register record, ArchitecturalDecision or parent requirement) and to each
  `Decision` column id that names a projected register record; `verified_by` to the test `Script` of each test node
  (three forms: `path::node`, a backticked test file followed by backticked test names, a test file alone); `satisfies`
  from the task the status names. The state walks the domain machine to `requirements.status_map`'s target; a row
  mapped to `verified` with no test is held at `implemented`. A re-import prunes edges the source no longer names.
- Everything that does not resolve is listed per row, not dropped.
- Domain (`seldon/domain/research.yaml`): the type's properties (`set_by` documentation; `document`, `section` and the
  verbatim columns as `trace`); `verified_by` and `derived_from` widened to `SRS_Requirement`; `rejected` reachable
  from `accepted` and `stale`, and `implemented -> stale` added, so a re-import can move a row back to open or withdraw
  it.

## Part C: the projection and the checks

- `seldon docs generate requirements|rtm` renders every `docs.projections` entry of that kind: only the blocks between
  `<!-- seldon:projection ... -->` and `<!-- /seldon:projection -->` are rendered (a table block per section; an inline
  `view="counts"` block for the counts sentence), so prose stays. Line 1 names the graph revision (sha256 of the
  rendered blocks, no timestamp: an unchanged graph renders the same bytes and commits nothing). The command commits
  the files it changed, path-scoped, through the hooks; `--check` writes nothing and exits 1 on a difference;
  `--no-commit` writes only. An existing file with no markers is refused, never overwritten; an absent one is rendered
  whole. A block's `headers` attribute picks the projection's columns by label, so one file's tables may differ.
- `seldon req import --mark` wraps the loaded tables in markers once, with their section and header labels.
- `seldon docs check` adds a REQUIREMENTS section (and a `requirements` key in `--json`); `--strict` fails on it.
  `seldon verify` has a new advisory check, **Requirements** (21 checks now), warning on requirements with no test
  (rejected ones excepted) and on each projection that differs from a fresh render, naming whether the graph moved or
  the file was edited by hand.

## Part D: hazbrief-mcp loads

Run with this branch's code (`python -m seldon` with `PYTHONPATH` at the worktree, cwd hazbrief-mcp's primary),
after HB-144 merged (see Outcome). hazbrief commits, all through its hooks, path-scoped:

| Commit | What |
|---|---|
| `56bfb6f9` | `register: numbered 337 record events merged from HB-144`: `seldon decision number` on the primary (the merge had not; defect fixed here). Then `seldon decision project`: 995 `Decision` nodes (308 hazbrief, 687 imported), REGISTER.md rendered. |
| `88c4fba6` | The adoption: `seldon.yaml` gains `requirements:` (the status map for both files' vocabularies and the counts template) and `docs.projections` (three files); `seldon req import --mark` on both files (149 + 65 created, 410 links, 199 test nodes); the two counts sentences wrapped in counts blocks. |
| `2ec3b5a4` | hazbrief's own dispatcher reconciled the 3,127 event lines the projection and the imports appended (AD-038-R1), between my commits. |
| `df4ab54c` | `seldon docs generate requirements`: `docs/VIEW_REQUIREMENTS.md` and `docs/submission/EVALUATION.md` rendered (revisions `24b121aee2dbaff5`, `28a3635affdc0dc7`). |
| `0241486a` | `seldon docs generate rtm`: `docs/REQUIREMENTS_TRACE.md` rendered (revision `5b55afa91c84fa9a`). |

- **Idempotence, measured:** a second `seldon req import docs/VIEW_REQUIREMENTS.md` wrote 0 events (149 unchanged).
- **The same bytes twice:** the three revisions equal those of a dry run made first on scratch copies against a scratch
  database (`/tmp/sel033/hbsim`, dropped after), so the render depends on the graph's content, not on when it ran.
- **States:** VIEW 117 verified, 5 implemented (`satisfied` with "none yet": held below verified by AD-013-R1), 24
  accepted, 3 rejected; RTM 34 verified, 16 implemented, 13 accepted, 2 rejected.
- **Checks on hazbrief:** `check_requirements` warns "214 requirement(s): 49 unverified, 0 projection finding(s)";
  `check_decisions` passes ("Register verifies; every label registered; projection current"); `docs generate
  requirements --check` and `rtm --check` exit 0.
- **hazbrief's tests:** `tests/test_view_requirements.py` 9 passed on the primary after the render (it holds the table,
  the export `docs/evidence/hb134/rtm.md` and the counts sentence in REQUIREMENTS_TRACE.md and EVALUATION.md; all still
  agree, and the export was not touched).
- **Timing:** hazbrief's dispatcher took its lease again (HB-145, registered 37e775a8) while I committed `88c4fba6`
  onward. HB-145 names a legend layer; if it edits VIEW_REQUIREMENTS rows by hand, its rebase meets the marker lines.
  The return tells hazbrief how to change a row now.

## Part E: the register warning

- `seldon/core/decisions.py` `NO_REGISTER_NOTICE`, `register_notice`. `seldon verify`'s Decision register check now
  **warns** "no decision register declared (AD-033); rulings made in this project have no record" with the one-block
  remedy (it passed as "skipping" before); `seldon go` prints a `## Decision register` section and a
  `decision_register` JSON key when the block is absent; `seldon init` prints the warning; `seldon project new`
  declares `decisions.repository: <directory name>` by default (a new `decisions` step; an empty `decisions:` key is
  refused, not overwritten).
- hazbrief's register was not created here, as the task says. hazbrief declared it itself in HB-144, which was running
  when this task reached Part D (see Part D).

## Part F: the return

`seldon cc return --to hazbrief-mcp --answers seldon:<SEL-031>` files hazbrief's return from the `## For hazbrief-mcp` section below; one return answers both filings (SEL-029: one return per answering task). Filed: hazbrief-mcp **HB-146** (task `1daf117b`, `cc_tasks/2026-11-09_HB-146_requirements_and_decisions_live_in_the_graph_the_rtm_and_the_requireme.md`, registered and committed there, `0db744ef`/`4f4b732b`); seldon's filings SEL-031 (`bd76c760`) and SEL-032 (`e3e93788`) are `completed` against it (AD-036-R17).

## Tests

- `tests/test_sel033_requirements.py` (26): the readers (tables, key map, status words, the three test-reference forms,
  round-trip cells, the state walk, block columns); the import (trace and states, a Decision column, unresolved
  listing, idempotence, a re-import that moves state and prunes, dry run, `req add`, the CLI with `--mark`); the
  projection (byte-identical tables with prose kept and a commit, a graph change and a hand edit each reported, an
  unmarked file refused, an absent RTM rendered whole from edges, an unplaced requirement appended, the CLI with
  `--check`); the checks (`verify`, `docs check --json` and `--strict`, one append per load).
- `tests/test_sel033_register_warning.py` (13): verify, go, init, project new, and a register a branch declares is numbered at its merge.
- Changed: `tests/test_go.py` (the new `decision_register` key), `tests/test_verify_event_log.py` (21 checks).
- Full suite on the final code (`-n 6`, 24 min): **3307 passed, 3 failed, 7 skipped**. The three are known and not
  this task's: `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` (library
  index drift, fails on main), and two timing tests under load (avg 12-17) that pass alone, re-run here: 
  `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` and
  `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`
  (2 passed). An earlier full run caught five of mine, all fixed before this one: the `Document` target (AD-030
  section 4, see Outcome), the SEL-021 and relationship-type fixtures for the widened edges, `test_verify`'s clean
  project (it now declares an empty register, since a project without one warns and a warning exits 1), and
  `test_dispatch_first_article` (a timing flake; passes alone).
- Also added after that run: `TestARegisterDeclaredOnABranchIsNumberedAtItsMerge` (2 tests, written first and seen
  failing on the old `number_merged_register`).

## Findings about hazbrief's files (a difference is a finding about the files, not the graph)

Every difference between the hand-kept files (`56bfb6f9`) and the rendered ones (`0241486a`), from
`git diff 56bfb6f9 0241486a -- docs/VIEW_REQUIREMENTS.md docs/REQUIREMENTS_TRACE.md docs/submission/EVALUATION.md`
(71 insertions, 4 deletions):

1. **No table row differs.** 214 rows in 33 tables (25 in VIEW, 8 in the RTM) render byte-identical.
2. **Added lines:** one `seldon:projection-revision` header on line 1 of each file, and a start and an end marker
   around each of the 33 tables (66 lines). Nothing else is added.
3. **Two sentences reflowed.** The counts sentence in REQUIREMENTS_TRACE.md ("The table at HB-139: ...") and in
   EVALUATION.md ("At HB-139 the table holds ...") each spanned a line break; the counts block renders it on one line,
   so each paragraph's line breaks moved (4 deleted lines, 2 added). The words and numbers are unchanged, and
   hazbrief's test normalises whitespace.
4. **Not projected, by design:** VIEW's `Set-by keys` table and the RTM's `Open findings` table (F-1 to F-5) are not
   requirements tables and stay hand-written; so does every paragraph of prose.

Findings about the files the load made visible (about the files, not the graph):

5. **176 `Set by` references do not resolve** (listed per row by the import): hazbrief's design notes (DN-001 to
   DN-022 and their addenda, 148 references) are not artifacts in its graph, neither DesignNote nor Document; and task
   addenda (`HB-115-A01`, `HB-130R-A01`, ..., 28 references) are files, not artifacts. 44 `derived_from` edges were
   made, to the base tasks the keys name. Registering the notes as DesignNotes would resolve the rest on re-import.
6. **The RTM has no `Set by` column.** Its rows' source is the section heading ("DN-001 section 3: scope"), so
   `seldon docs check` counts its 65 rows incomplete on `set_by`. Its `Decision` column (HB-144) gives 73
   `derived_from` edges to register records instead, every one resolved.
7. **49 requirements have no verifying test** (rejected ones excepted): VIEW's 31 "none yet" rows less its withdrawn
   ones, and 21 RTM rows whose `Checked by` names a harness, "inspection", "judged, not tested", or test functions with
   no file (E-D2 to E-D6 cite `test_...` names alone, so no node id can be formed).

## For hazbrief-mcp

**SEL-031 and SEL-032 are one defect, answered together** by seldon SEL-033 under
`docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md` (rulings AD-013-R1 to R3, AD-033-R13): the governance
layer was declared and never wired.

**SEL-031 (the register):**
- *Optional?* No. AD-033-R1 already made the register every task-registering repository's; nothing read it. Now
  `seldon init`, `seldon go` and `seldon verify` say "no decision register declared (AD-033); rulings made in this
  project have no record", and `seldon project new` declares one by default (AD-033-R13).
- *Refuse or warn?* Warn. Declaring the register is the project's one-block act, and a Tier A failure would hold every
  task of a project that has not made it yet.
- *The route after the fact:* the one block hazbrief declared in HB-144 (`decisions: {repository: hazbrief-mcp}`),
  then `seldon decision propose|accept --from <record.yaml>`. A ruling made in a chat cites the chat as a receipt (its
  URL and date) with `--operator-stated`; its `source` is the note, RESULT or handoff that quotes it.
- *What went wrong after HB-144, and is done:* its merge numbered none of its 337 pending records (the merge read the
  pre-merge config; a seldon defect, fixed in SEL-033). SEL-033 ran HB-144 RESULT's recipe on hazbrief's primary:
  numbered (`56bfb6f9`; `seldon decision check`: clean) and projected (995 `Decision` nodes). `seldon verify`'s
  register check passes on hazbrief.

**SEL-032 (the requirements):**
- *The type?* `SRS_Requirement` exists and is now loadable (`seldon req import <table> [--mark]`, `seldon req add
  <id> ...`), renderable (`seldon docs generate requirements|rtm`, committed, revision-stamped) and counted
  (`seldon verify` "Requirements"; `seldon docs check`).
- *The load route, done for you:* VIEW_REQUIREMENTS.md (149 rows) and REQUIREMENTS_TRACE.md (65 rows) are in the
  graph, with `derived_from` (sources and `Decision` records), `verified_by` (test nodes) and `satisfies` (tasks).
  Both files and EVALUATION.md's counts sentence are projections now (`88c4fba6`, `df4ab54c`, `0241486a`). No row's
  text changed; your `tests/test_view_requirements.py` passes.
- *Verify counts:* 49 requirements have no verifying test today.

**What hazbrief does now:**
1. **Change a requirement in the graph, not the table:** `seldon req add VR-150 --statement "..." --set-by "DN-022 §4"
   --verified-by tests/x.py::test_y --status "open: ..." --section "<heading>" --document docs/VIEW_REQUIREMENTS.md`
   (or edit the table and re-run `seldon req import docs/VIEW_REQUIREMENTS.md`), then `seldon docs generate
   requirements` and `seldon docs generate rtm`; each commits its files. This replaces the four-place ratchet step in
   every task that touches a row (HB-134R2). `seldon docs check` reports a table edited outside the graph.
2. **Tasks in flight:** a task that edits VIEW rows by hand (HB-145 was launched while this landed) rebases over the
   marker lines; after it merges, re-run `seldon req import docs/VIEW_REQUIREMENTS.md` and `seldon docs generate
   requirements` once.
3. **Optional, your call:** register the DN notes as DesignNote artifacts so the 148 note references in `Set by`
   resolve on the next import; give the 49 unverified requirements a test or a row note.
4. These commands are on seldon's main once SEL-033 merges; until then hazbrief's `seldon` runs the previous code.
