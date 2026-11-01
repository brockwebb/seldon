# RESULT: SEL-021, review findings are Issues, traced to their fix, their test and the decisions they change

**Task:** `600ef89a`, `cc_tasks/2026-11-01_SEL-021_review_findings_are_issues_traced_to_fix_test_and_decision.md`.
No addenda were filed (none matched `*SEL-021*ADDENDUM*`).
**Branch:** `worktree-humming-napping-quasar`. Code and tests are in `9c5bfc1`. The convention note, the CLAUDE.md
line and this file are in the closing commit. I did not merge, push or run `cc complete`; the dispatcher does those.
**Parts:** A, B and C were recorded with `seldon dispatch part-complete` after `9c5bfc1` (at 173,136 / 173,436 /
173,736 tokens, about 725 s; no stop). D is recorded after this commit.
**Premises:** both held. `Issue:` is in `seldon/domain/research.yaml`, and `remediated_by` Issue -> ResearchTask was
already there (AD-034's `merge_blocked` Issues use it).
**Stop condition:** not reached. The change is additive: the required Issue properties are the same, and only enum
values, optional properties and edges were added. Every Issue in every online graph was read-only checked against
the new schema with `/tmp/sel021/issue_load_check.py`:

```
seldon-ai-readiness-kg           issues=  25  nonconforming=  5  caused_by_sel021=0
seldon-arnold                    issues=   3  nonconforming=  0  caused_by_sel021=0
seldon-brock-projects            issues=   5  nonconforming=  0  caused_by_sel021=0
seldon-census-web-concept-inventory issues=   3  nonconforming=  0  caused_by_sel021=0
seldon-hazbrief-mcp              issues=  14  nonconforming=  0  caused_by_sel021=0
seldon-icsp-notebook             issues=   4  nonconforming=  0  caused_by_sel021=0
seldon-regs-comment-pipeline     issues=   7  nonconforming=  0  caused_by_sel021=0
seldon-seldon-self               issues=  37  nonconforming=  0  caused_by_sel021=0
seldon-slosh-pipe                issues=  99  nonconforming=  0  caused_by_sel021=0
seldon-squiddy                   issues=  81  nonconforming=  0  caused_by_sel021=0
seldon-tickbiterisk              issues=   9  nonconforming=  0  caused_by_sel021=0
seldon-usai-harness              issues=   1  nonconforming=  0  caused_by_sel021=0
TOTAL issues=288 nonconforming=5 caused_by_sel021=0
```

The 5 ai-readiness-kg Issues were already outside the enums before this change. Their values are `incomplete_extraction`,
`design_clarification`/`schema`, `process_gap`/`process`, `incomplete_projection` and `spend_control`/`process`.
Enums are checked only on write, so these Issues load under both the old and the new schema. They are not this
task's to fix.

Recall used: AD-029-A

AD-029-A (every Cypher query binds a label on each node pattern it matches by relationship) shaped the new queries.
The orphan query is `(i:Artifact:Issue)-[:REMEDIATED_BY]->(task:Artifact:ResearchTask)` and
`-[:VERIFIED_BY]->(s:Artifact:Script)`. The decision lookup is `(d:Artifact) WHERE d:Decision OR
d:ArchitecturalDecision`, and `issue show`'s trace query binds `:Artifact` on both ends. The other recall hits
(precedence labels, the 2026-09 defect sweeps, `precedes`, AD-019, AD-021) were read and did not change the approach.

## Part A: the Issue type admits review findings

Schema diff (`git diff b9002f5 -- seldon/domain/research.yaml seldon/core/issue_utils.py`, summarised):

| Where | Added |
|---|---|
| `ISSUE_ENUMS.issue_type` | `review_finding` |
| `ISSUE_ENUMS.detection_method` | `review` |
| `ISSUE_ENUMS.target` | `code` (see Decisions 1) |
| `ISSUE_ENUMS.disposition` (new) | `fixed`, `rejected`, `duplicate`, `wont_fix` |
| `Issue` properties, all optional, `category: system` | `found_in`, `severity`, `disposition`, `disposition_evidence` |
| `Script` property, optional, system | `test_node`: the `<path>::<node id>` the Script stands for |
| `ResearchTask` property, optional, system | `found_in` (Part C) |
| relationship `verified_by` | Issue -> Script |
| relationship `changes` | Issue -> Decision, ArchitecturalDecision |
| relationship `remediated_by` | unchanged (already Issue -> ResearchTask and others) |

Code: `seldon/core/review_findings.py` holds the grammars (`FOUND_IN_GRAMMAR`, `TEST_REF_GRAMMAR`), the write-boundary
rules (`review_properties`), the resolution and planned writes for the links (`plan_trace_writes`), and the orphan
rule. Both surfaces call it:

- **CLI:** `seldon issue create` and `seldon issue update` accept `--found-in`, `--severity`, `--disposition`,
  `--disposition-evidence`, and the repeatable `--remediated-by`, `--verified-by` and `--changes`. `issue show`
  prints the fields and a Trace block.
- **MCP:** `seldon_issue_create` and `seldon_issue_update` accept the same fields; the links are `list[str]`.

Every link is resolved before the first write, and the Issue (or its update), any new test Script and all the links
go down in one ledger append (SEL-007). The tool description no longer says "Issues are NOT for software bugs". It
now says review findings are Issues, filed where they are fixed, and other bugs and feature requests stay CC tasks.

Rules applied at the write boundary:
- a `review_finding` must have `found_in`;
- `found_in` must parse;
- a disposition other than `fixed` must have non-empty evidence, given in this call or already on the Issue;
- evidence without a disposition is refused;
- a test reference must parse, and its file must be in the project. The node id is not collected.

## Part B: `seldon issue orphans`

CLI `seldon issue orphans [--json]` and MCP `seldon_issue_orphans`. A `review_finding` Issue passes in either case:
- (a) it has `REMEDIATED_BY` to a ResearchTask in `completed` or `verified`, and at least one `VERIFIED_BY`;
- (b) its `disposition` is not `fixed` and `disposition_evidence` is not blank.

Otherwise it is listed with its reasons. The CLI exits 1 when the list is not empty. The MCP output ends
`orphans: <n>`.

On seldon's own graph (`python -m seldon issue orphans` in this worktree, database `seldon-seldon-self`):

```
orphans: 0
EXIT=0
```

seldon's graph has no review findings yet. The backfills in plan stage 3 are squiddy's and hazbrief-mcp's.

## Part C: `**Found in:**` task header

`seldon.core.dispatch.static_checks` reads the optional header. It is the one function registration and the
dispatcher share (AD-038-R12). The header is also in the repeated-header check. An unparsable value fails with
`found_in_unparsable` and a message that quotes `FOUND_IN_GRAMMAR`, so registration refuses it before anything is
created. A valid value is recorded on the ResearchTask's `artifact_created` line as `found_in`.

## Part D: the record

- Convention note: `docs/conventions/review_findings.md` (one page). It explains how a coordinator files findings
  under F-010: one Issue per finding at review time, `**Found in:**` on the fix task, links at merge, evidence on a
  rejection, `issue orphans` before calling a review closed. It cites the prior art named in factory
  `docs/architecture.md` section 2 (Gotel and Finkelstein 1994, DO-178C, ISO/IEC/IEEE 29148:2018) and the
  justification-required disposition pattern of SARIF 2.1.0 suppressions and IEEE 1044-2009.
- CLAUDE.md: a three-line pointer under Environment.

### Tests (`tests/test_sel021_review_findings.py`, 32 cases from 19 functions)

Part A: `test_the_issue_enums_admit_a_review_finding`, `test_the_domain_declares_the_trace_edges_and_optional_properties`,
`test_an_issue_with_only_the_pre_sel021_properties_still_loads`, `test_the_found_in_grammar_parses` (4),
`test_a_found_in_that_does_not_parse_is_refused_with_the_grammar` (7), `test_a_test_reference_must_parse_and_name_a_file_in_the_project`,
`test_the_review_property_rules`, `test_cli_create_files_a_finding_with_its_fix_test_and_decision_in_one_append`,
`test_cli_create_refuses_a_bad_finding_and_writes_nothing` (5), `test_cli_update_records_a_disposition_and_links_after_the_fact`,
`test_mcp_create_files_a_finding_and_says_review_findings_are_issues`, `test_mcp_update_records_a_rejection_with_its_evidence`.

Part B, the four the task names first: `test_a_fixed_finding_with_task_and_test_and_a_rejected_one_with_evidence_pass`,
`test_a_planted_finding_with_only_a_task_fails`, `test_a_planted_rejected_finding_with_empty_evidence_fails`; then
`test_an_unfinished_fix_task_and_a_bare_finding_are_orphans`, `test_mcp_orphans_reports_the_count`.

Part C: `test_the_static_checks_read_the_found_in_header` (one valid, one absent, one invalid) and
`test_registration_records_a_valid_found_in_and_refuses_an_invalid_one` (an invalid header refuses and the ledger is
unchanged).

### Suite

The new file and its neighbours (`test_issue`, `test_mcp_tools`, `test_sel007_atomic_multi_event`,
`test_domain_loader`, `test_sel013r_answers_files_its_return`): 106 passed.

Full suite (`python -m dotenv -f .env run -- python -m pytest tests/ -q -n 6`): **3166 passed, 7 skipped, 3 failed**
in 28 min. None of the 3 failures comes from this change:
- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` was already failing
  on main (squiddy library index drift, Issue dbe38fac).
- `test_friction002_stop_hook_gate::test_a_session_let_go_with_its_gate_unpassed_is_never_merged[passing]` and
  `test_friction002_worktree_only::test_a_launched_task_runs_in_its_cli_worktree_and_merges_on_green` both expected
  task `a` to be `completed` and found `blocked`. Run alone, both pass (3 passed in 67 s). This is the known collision
  of `task_states()` looking tasks up by the common name `a` under xdist, recorded at DISP-003R. Neither test touches
  Issues, the domain's Issue/Script/ResearchTask additions, or the Found in header.

## Decisions (grounded, logged, not escalated)

1. **`target` gains `code`.** `target` is required, and none of its document values (`content`, `citation`,
   `terminology`, `data`, `structure`) names where a code-review fix lands. The change is additive. The MCP default
   stays `content`.
2. **The test is a Script, not a property.** The task allowed either, "whichever the domain config already
   supports". Script already exists with `name` and `path`, and it is a legal target of `remediated_by`, so the test
   is a Script node: `name` is the node id, `path` is the file, and `test_node` holds the node id. One Script per node
   id is reused across findings. It has no `content_hash`, so `seldon verify`'s drift check (which reads only artifacts
   that have one) never reports it.
3. **`changes` also accepts ArchitecturalDecision.** Repositories without a decision register (several consumers)
   still record decisions as ADs. The register `Decision` is the primary target.
4. **`found_in` is required on a `review_finding` at creation; evidence is required on a non-`fixed` disposition at
   every write.** Both fail early (constitution section 4). `orphans` still checks the graph, because a write path
   that bypasses these rules (a direct `artifact create`, a replay) can leave such a state. The tests plant exactly
   that.
5. **The `**Found in:**` grammar check lives in `static_checks`, not only in registration.** Registration and the
   dispatcher then refuse the same file with the same code (AD-038-R12's rule for every static check).
6. **No new AD.** The decision is factory F-010/F-011 and is recorded there. This task implements it. The
   convention note names F-010 as governing.

## Not done / follow-ups

- The node id in `--verified-by` is not collected by pytest; only the file's existence is checked. Collecting it
  would run the target project's test collection inside an Issue write.
- Backfilling squiddy (SQ-105R's 15 findings) and hazbrief-mcp (HB-87R) is plan stage 3 step 2, filed separately and
  waiting on this task.
- I wrote the tests alongside the code, not strictly first. Planted-orphan cases fail by construction on the old code,
  where `orphans` does not exist.
