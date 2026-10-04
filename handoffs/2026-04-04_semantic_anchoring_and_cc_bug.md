# Session Handoff: Semantic Anchoring Design + cc_complete Bug Discovery

**Date:** 2026-04-04
**Projects:** seldon (primary), ai-workflow-design (secondary)
**Context:** Started from Medical AI Scientist paper review (arXiv:2603.28589v1), extracted two patterns for Seldon's writing pipeline, designed graph-native implementation, discovered cc_complete bug during ai-workflow-design session.

---

## What Happened

### Pattern Extraction from Medical AI Scientist Paper
Reviewed Wu et al. (2026) "Towards a Medical AI Scientist" paper and project homepage. Extracted two patterns relevant to Seldon's writing/review pipeline:

- **Pattern A (Semantic Anchoring):** Compressed summaries of prior sections used as context during drafting. Adapted from their linear "previous sections" model to a **bidirectional dependency map** — all sections anchor all other sections, with `depends_on_me` as the critical addition for revision blast radius.
- **Pattern B (Narrative Logic Assessment):** Post-draft pass evaluating whether prose argues vs. merely describes. Deferred for implementation — design captured in design note with parking lot of additional checks.

### Design Note Written
`seldon/docs/design/2026-04-04_semantic_anchoring_and_narrative_logic.md` — covers both patterns with rationale, provenance, schema design, and integration points.

### Graph-Native Implementation (Not Flat Files)
Initial CC task was a one-off flat-file approach (YAML anchors in `anchors/` directory). Caught the mistake — this is Seldon capability, not a project-specific hack. Rewrote as two CC tasks:

1. **Seldon schema + command** — add documentation properties to PaperSection, add `assumes` relationship type, add `seldon paper context <section>` command
2. **ai-workflow-design population** — use new schema to populate all 14 chapters and create `assumes` edges

### Neo4j Native Lists Decision
Properties like `claims`, `terminology_defined`, `forward_promises` use native Neo4j list types (`list[str]`). No pipe-delimited string encoding. The driver, JSONL event store, and graph all handle lists natively. Zero reason for artificial serialization friction.

### cc_complete Bug Discovered
During ai-workflow-design session, attempted to use `seldon_cc_complete` on tasks previously registered with `seldon_cc_register`. Bug confirmed:

**Root cause:** `cc.py` line 90-96. `_find_existing()` queries for any ResearchTask with matching `source_file` regardless of state. When `cc_register` pre-creates the artifact in `proposed` state, `cc_complete` finds it, prints "already recorded as completed," and exits without calling `_walk_to_completed()`. The artifact stays `proposed` forever. The warning message is also misleading — says "completed" when state is actually `proposed`.

**The fix:** When `_find_existing` returns an artifact, check its current state. If already `completed`, warn and exit (true duplicate). If `proposed`/`accepted`/`in_progress`, walk it to `completed` via the existing `_walk_to_completed()` function. The MCP `seldon_cc_complete` tool in `mcp_server.py` likely has the same pattern and needs the same fix.

**Impact:** Every CC task that was registered via `cc_register` (Desktop) and then completed via `cc_complete` (CC) is stuck in `proposed` state in the graph. This affects both seldon and ai-workflow-design projects. The `seldon go` output shows them as "open tasks" when they're actually done.

---

## Files Written

### seldon repo
| File | Type | Status |
|------|------|--------|
| `docs/design/2026-04-04_semantic_anchoring_and_narrative_logic.md` | Design note | Written |
| `cc_tasks/2026-04-04_semantic_anchor_schema_and_context_command.md` | CC task | Registered in graph (`149d34d4`) |

### ai-workflow-design repo
| File | Type | Status |
|------|------|--------|
| `cc_tasks/2026-04-04_populate_semantic_anchors.md` | CC task | Registered in graph (`7f9b94cb`), blocked on Seldon task |
| `cc_tasks/2026-04-04_implement_semantic_anchoring.md` | CC task | SUPERSEDED — old flat-file approach. Graph registration closed (`9884d7d2`). File on disk is historical. |

---

## Open Items

### HIGH PRIORITY: cc_complete bug
- **Issue not yet created in graph** — MCP server timed out during `seldon_issue_create`. Create on next session start.
- **Bug is in:** `seldon/seldon/commands/cc.py`, duplicate guard in `cc_complete` function (line ~90-96). Also check `mcp_server.py` for same pattern.
- **Fix scope:** Small — add state check after `_find_existing`, call `_walk_to_completed` if not already completed.
- **Remediation:** After fix, need to walk all pre-registered-but-stuck-proposed tasks to completed in both projects.

### Seldon CC Task: Schema + Context Command
- `cc_tasks/2026-04-04_semantic_anchor_schema_and_context_command.md` — ready for CC execution
- Adds: PaperSection doc properties, `assumes` relationship type, `seldon paper context` command
- Full path: `/Users/brock/Documents/GitHub/seldon/cc_tasks/2026-04-04_semantic_anchor_schema_and_context_command.md`

### ai-workflow-design CC Task: Populate Anchors
- `cc_tasks/2026-04-04_populate_semantic_anchors.md` — blocked on Seldon task
- Populates all 14 chapters with anchor properties, creates `assumes` edges
- Full path: `/Users/brock/Documents/GitHub/ai-workflow-design/cc_tasks/2026-04-04_populate_semantic_anchors.md`

### Seldon Graph Task: Register Design Note
- Task `50584cf1` (proposed) — register the semantic anchoring design note as graph artifact with `informs` edges to AD-020 and AD-014. Can bundle into the schema CC task execution.

### From Previous Sessions (still open)
- 4 deferred Seldon design tasks from March 25 hotwash (all proposed)
- Ch 8 AD-020 pipeline run (next after semantic anchoring is populated)
- Em-dash purge + `\$` escaping (foreword–Ch 2) — medium priority
- Session 17 flagged citations — low priority

---

## Execution Order

1. **Fix cc_complete bug** (small, high priority — write CC task or fix directly)
2. **Remediate stuck proposed tasks** in both repos (walk to completed)
3. **Seldon CC task:** schema + context command (`149d34d4`)
4. **ai-workflow-design CC task:** populate anchors (`7f9b94cb`)
5. **Ch 8 AD-020 run** using `seldon paper context chapter-08` as context input

---

## Key Decisions

1. **Bidirectional anchoring over linear.** The book has 14 drafted chapters being revised non-linearly. Anchors must show blast radius in both directions (what depends on me, what I depend on), not just "prior chapters."

2. **Graph-native over flat files.** Properties on PaperSection nodes + `assumes` edges in the graph. Not YAML files in an `anchors/` directory. Seldon capability, not project-specific hack.

3. **Neo4j native lists over pipe-delimited strings.** The driver handles `list[str]` natively. No serialization layer needed.

4. **`assumes` distinct from `cross_references`.** `cross_references` = explicit in-text mention (mechanical, detected by `paper sync`). `assumes` = implicit dependency (semantic, proposed by CC/human). Different provenance, same graph machinery.

5. **Pattern B deferred.** Design captured in design note with parking lot. Implement after Pattern A is dogfooded on 2-3 chapters — the observation will sharpen Pattern B's scope.
