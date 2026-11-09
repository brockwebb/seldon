# SEL-033: requirements and decisions live in the graph, the RTM and the requirements table are projections of it, and a project without a decision register is told so

**Status:** proposed
**Author:** Desktop session (seldon), 2026-11-09, answering hazbrief filings SEL-031 (`cc_tasks/2026-11-09_SEL-031_...md`) and SEL-032 (`cc_tasks/2026-11-09_SEL-032_...md`) together, as SEL-032 asks.
**Repo:** seldon (primary); hazbrief-mcp (Part D loads its 148 view requirements and Part F files the return). L4: commit, merge, push in both.
**After:** none
**Governing:** AD-002 (domain-agnostic engine, domain config is schema); AD-006 (every cited quantity is a graph artifact with provenance; the same rule for requirements); AD-013 (documentation as traceability, which already declares `SRS_Requirement`); AD-012 (paper as graph assembly: files are projections); AD-033 (the decision register); AD-030 (governed documents as graph content). Number new rulings under AD-013 (the requirement type and its projection) and AD-033 (the register warning).
**Model:** primary
**Spend:** est. 1.4M tokens. Basis: one design note with its prior-art pass, one importer, one renderer with two views, one verify count, one warning in four commands, the hazbrief load, the return. Zero model calls: the importer reads a markdown table, it does not extract.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits the domain config, `seldon docs`, `seldon verify`, `seldon init`, `seldon project new`, `seldon go`)
**Parts:** A 0.20, B 0.20, C 0.20, D 0.15, E 0.10, F 0.15.
**Premises:**
- premise: SRS_Requirement is already a research-domain artifact type with a state machine | check: grep -q "SRS_Requirement:" seldon/domain/research.yaml
- premise: nothing renders requirements from the graph today | check: sh -c "! grep -q SRS_Requirement seldon/commands/docs.py"
- premise: the trace edges exist in the domain config | check: grep -q "^  satisfies:" seldon/domain/research.yaml
- premise: hazbrief declares no decision register | check: sh -c "! grep -q '^decisions:' /Users/brock/GitHub/hazbrief-mcp/seldon.yaml"
- premise: hazbrief's requirements table is the first dataset | check: test -f /Users/brock/GitHub/hazbrief-mcp/docs/VIEW_REQUIREMENTS.md
- premise: seldon's own register is declared | check: grep -q "^decisions:" seldon.yaml

Checks are single commands with no shell.

Read SEL-031 and SEL-032 in full before Part A; they are the measurement.

## The condition

The design has said since AD-002 and AD-006 that the graph is the truth and documents are projections, and AD-013 declares `SRS_Requirement` with `requirement_id` and `description`; `seldon/domain/research.yaml` carries the type, a state machine (proposed, accepted, implemented, verified, stale, rejected) and the edges `implements`, `validates`, `satisfies`, `verified_by`, `derived_from`. Nothing loads requirements into it except `seldon artifact create` by hand, nothing renders them out, and `seldon verify` does not count them. seldon's own graph has 37 events on the type; hazbrief's has one. So hazbrief wrote its 148 view requirements and its RTM as markdown (`docs/VIEW_REQUIREMENTS.md`, `docs/REQUIREMENTS_TRACE.md`, `docs/evidence/hb134/rtm.md`), the graph holds their hashes, and HB-134R2's "four-place ratchet" keeps counts identical by hand across four files; HB-131R, HB-136R, HB-140R, HB-141 each paid for it. Rulings made in hazbrief Desktop chats have no record because the project declares no `decisions:` block, and `seldon init`, `seldon go` and `seldon verify` were silent about that for twenty days, 143 tasks and seventeen design notes. SEL-031 and SEL-032 are one defect: the work layer (tasks, issues, scripts, results) was modelled in the graph; the governance layer (requirements, decisions, tests, traces) was declared and never wired. ANTS v0.4 had `export_rtm` and `export_coverage_report` over the same shape and they did not carry forward (AD-001).

## Prior art, to be received in seldon's log in Part A

IEEE/ISO/IEC 29148 (requirements attributes and traceability); ReqIF (OMG, the interchange shape: a requirement is an object with typed attributes and typed relations, not a row); SysML v2 requirement and satisfy/verify relations; IBM DOORS (the operator's reference: a module is a view over a database, the document is generated); Gotel and Finkelstein 1994 on traceability; Cleland-Huang on trace link maintenance. Seldon's edges already match the ReqIF/SysML relation set.

## What to build

**A. The design note.** `docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md`: re-run the prior art above through `seldon prior-art search`; rule that a requirement is a graph artifact (statement, id, source decision or note, state, `verified_by` a Test or check, `satisfies`/`implements` edges to ResearchTask, Script, Document; `derived_from` for hierarchy), that a requirements table and an RTM are projections rendered from it, that a governed markdown requirements file is a load source and never the truth, and that a seldon-managed project with no `decisions:` block is reported at init, go and verify. `prior-art verify` passes before B to F.

**B. Load.** `seldon req import <markdown table> [--id-column ...]` creates or updates `SRS_Requirement` artifacts from a numbered table (id, statement, set-by, validated-by, state), idempotent on id, linking `satisfies` to the ResearchTask or note the set-by names and `verified_by` to the test the validated-by names when they resolve, and listing what did not resolve. Also `seldon req add` for one.

**C. Project.** `seldon docs generate requirements` and `seldon docs generate rtm` render the table and the matrix from the graph into paths `docs.projections` declares, committed by the command (AD-038-R15), with a generated header that names the graph revision; the counts sentence is rendered, so the ratchet is retired. `seldon docs check` reports a requirement with no `verified_by` and a requirement whose rendered file is older than its graph state.

**D. hazbrief loads.** Import `docs/VIEW_REQUIREMENTS.md` (148 VR rows) and `docs/REQUIREMENTS_TRACE.md`; render both projections to the same paths; diff against the hand-kept files and record every difference in the RESULT (a difference is a finding about the files, not the graph). Declare `docs.projections` in hazbrief's seldon.yaml. Commit through the hooks.

**E. The register warning.** `seldon init`, `seldon project new`, `seldon go` and `seldon verify` report "no decision register declared (AD-033); rulings made in this project have no record" when `decisions:` is absent; `project new` declares one by default. Do not create hazbrief's register here: SEL-031's return (Part F) tells hazbrief how, and hazbrief declares its own.

**F. The return.** `seldon cc return --to hazbrief-mcp` answering SEL-031 and SEL-032 point by point: the type exists and is now loadable and renderable; the load route is B; verify counts are C; one defect, designed together, under AD-013 ADDENDUM 01; the register is declared by hazbrief with one block, and the rulings the hazbrief thread can recover from its design notes go in as `seldon decision propose` lines.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.7M.

## Deliverables

A to F with tests; the rulings; hazbrief's projections rendered and committed; `cc_tasks/2026-11-09_SEL-033_requirements_and_decisions_live_in_the_graph_and_the_rtm_is_a_projection_RESULT.md`.
