# SEL-032: the graph holds no requirement nodes; a project's RTM and its 148 view requirements are markdown files the graph knows only by hash, so "the graph is the source of truth" runs backwards for the requirements layer

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-09
**Reporter:** Desktop session (hazbrief-mcp), the same review as SEL-031.

## What was observed

1. hazbrief-mcp's graph, 2026-11-09: artifact types present are Issue (228), ResearchTask (166), Script (147), OntologyTerm (109), Document (37), LabNotebookEntry (2). No node is a requirement, a decision, a test or a trace.
2. The project's requirements exist: `docs/VIEW_REQUIREMENTS.md` (148 numbered VR rows, each with Set-by, Validated-by and a state, HB-134R2), `docs/REQUIREMENTS_TRACE.md`, their export `docs/evidence/hb134/rtm.md`, and `docs/submission/EVALUATION.md`'s counts. Each is one `Document` artifact with a `content_hash`. The graph cannot answer "which requirement does test X verify", "which requirements does decision Y constrain" or "how many requirements are unverified" except by a task re-parsing the markdown.
3. Consequence in practice: HB-134R2 instituted a "four-place ratchet", a rule that the counts sentence be kept identical by hand in four files, and every task since has carried the step. That is the work a projection from the graph would do. HB-131R, HB-136R, HB-140R and HB-141 each spend part of their budget on it.
4. The operator's expectation (2026-11-09): "the documents are generated from the graph. The graph should hold all the requirements." The operating contract in `seldon go` says the same ("Files are projections of graph state"). For requirements in this project the file is the truth and the graph holds its hash.

## What hazbrief-mcp wants to know back

- Whether Seldon intends a `Requirement` artifact type (statement, source decision, verifying test, state, trace edges to ResearchTask and Decision) and a `seldon docs generate` renderer for an RTM and a requirements table from it; or whether requirements are meant to stay in governed markdown with the graph holding the file.
- If the type is intended: the load route for an existing table (hazbrief's 148 rows are the first dataset), and whether `seldon verify` should count requirements with no verifying test the way it counts stale Results.
- Whether this and SEL-031 are one defect (the governance layer, decisions and requirements, was never modelled in the graph; only the work layer, tasks and issues, was) and should be designed together.

## Evidence

- `seldon_query` over hazbrief-mcp, 2026-11-09: `MATCH (n) RETURN labels(n)[0], n.artifact_type, count(*)`, the six types above.
- hazbrief-mcp `docs/VIEW_REQUIREMENTS.md`, `docs/REQUIREMENTS_TRACE.md`, `docs/evidence/hb134/rtm.md`; `cc_tasks/2026-11-08_HB-134R2_..._RESULT.md` (the ratchet).
- seldon filing SEL-031 (this repository, same date).
