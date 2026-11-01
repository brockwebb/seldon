# SEL-021: review findings are Issues, traced to their fix, their test and the decisions they change

**Status:** proposed
**Author:** the factory Desktop session (FCT-2), 2026-11-01.
**Repo:** seldon. L4: commit, merge, push. No other repo is written.
**After:** 2026-11-01_SEL-022_the_dd007_refusal_rings_the_stuck_alarm_once_and_stops_dirtying_the_log
**Governing:** factory F-010 (a review finding is an Issue, traced both ways) and F-011 (`found_in` cross-repo links); factory `docs/plan.md` stage 3 and `docs/gaps.md` G-08, G-10; F-002 (defect filed where it is fixed); FC-19 (dispatched records immutable).
**Model:** primary
**Spend:** est. 0.7M tokens. Basis: a domain-config change, two edge types, one CLI and MCP verb and one header, each with tests; SEL-019 at 0.5M for a comparable command. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** seldon/domain/research.yaml, seldon/commands/, seldon/core/, seldon/mcp/, tests/, docs/design/, docs/conventions/, CLAUDE.md
**Parts:** A 0.5, B 0.25, C 0.1, D 0.15.
**Premises:**
- premise: the Issue artifact type exists | check: grep -q "Issue:" seldon/domain/research.yaml
- premise: `REMEDIATED_BY` is already used between Issue and ResearchTask | check: grep -rqi "remediated_by" seldon/

Glob and read every sibling `*SEL-021*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.0M. Stop and report if an existing Issue in any graph would fail to load under the new schema (the change
must be additive).

## Why

A review finding today becomes a fix task and, at best, a sentence in a RESULT. SQ-105R fixed 14 of 15 squiddy
findings and rejected one; HB-87R fixed hazbrief's; none of it is in a graph as finding, fix, test and changed
decision. That is the DOORS gap the operator named in FCT-1: a change cannot be traced back to what asked for it,
or forward to what it altered. Seldon's Issue type is the right home but is documented as "not for software bugs".

## Part A: the Issue type admits review findings

- `issue_type` gains `review_finding`; `detection_method` gains `review`.
- New properties: `found_in` (`<repo>:<path>#<finding id>`, e.g.
  `factory:reviews/squiddy_code_review_max_findings.md#3`), `severity` (free text as the review states it),
  `disposition` (`fixed`, `rejected`, `duplicate`, `wont_fix`) and `disposition_evidence`.
- Edges: `REMEDIATED_BY` (to ResearchTask, existing), `VERIFIED_BY` (to the test: a `path::node id` reference,
  stored on a Script artifact or as a property, whichever the domain config already supports), `CHANGES` (to a
  decision record id in the register).
- `seldon_issue_create` and its CLI accept the new fields; the tool description's "not for software bugs" line is
  narrowed to say review findings are Issues.
- Additive only: every existing Issue loads unchanged.

## Part B: `seldon issue orphans`

CLI and MCP. Lists every `review_finding` Issue with neither (a) `REMEDIATED_BY` to a completed task plus
`VERIFIED_BY`, nor (b) a `disposition` other than `fixed` with non-empty evidence. Exits nonzero when the list is
non-empty. Tests: a fixed finding with task and test passes; a rejected finding with evidence passes; a planted
finding with only a task fails; a planted rejected finding with empty evidence fails.

## Part C: `**Found in:**` task header

Optional task-file header with the `found_in` grammar, parsed at registration onto the ResearchTask; an unparsable
value refuses registration with the grammar quoted. Test: one valid, one invalid.

## Part D: the record

RESULT: the schema diff; the test names; `seldon issue orphans` output on seldon's own graph; a convention note in
`docs/conventions/` (one page) saying how a coordinator files review findings under F-010.
