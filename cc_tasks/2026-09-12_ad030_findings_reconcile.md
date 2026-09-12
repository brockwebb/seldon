# CC Task: AD-030 findings reconciliation, ruling patterns, dependency pin, count verification

**Date:** 2026-09-12
**Governing docs:** `docs/design/AD-030_governed_documents_as_graph_content.md`; `docs/design/AD-030_implementation_findings_001.md` (rulings AD-030-R11 to R19). Read both in full before starting.
**Inputs:** `cc_tasks/2026-09-12_seldon_handoff_tool_RESULT.md`, `cc_tasks/2026-09-12_ad030_governed_docs_ingest_RESULT.md`
**Autonomy:** L4. Commit, merge to main, push, close the Seldon task named in the registration of this file. Do not ask the operator anything; decide, log the grounding in the RESULT, proceed.
**Addenda:** Glob and read all sibling `*ADDENDUM*.md` files before starting.

---

## Steps

1. **Ruling classification (AD-030-R16).** Edit the ruling patterns in `governed/config.yaml` under `domain:` so a Ruling requires a ruling identifier (`AD-NNN-Rn`, `DN-…-Rn`, numbered requirement ID) or `BINDING` as a heading token, at heading or first-token position. Body-prose `never`, `must`, `BINDING` no longer classify. Re-run the governed pipeline over the full corpus. AD-030 must yield exactly 10 Rulings, R1 through R10. Record the before/after Ruling count and list every Ruling that was dropped, with its `matched_pattern`, in the RESULT.

2. **Actor gate (AD-030-R11).** Confirm `seldon cc register`, `seldon_cc_register`, and the `seldon handoff` R9 gate exempt only `created_by = cc`. If the current implementation exempts by any other rule (e.g. gates only `desktop`), change it to the allow-list of one and add a test that an unknown actor string is gated.

3. **Dependency pin (AD-030-R17).** Pin Squiddy by commit hash in `governed/` (requirements file or Makefile variable, your call, state it). Confirm `pyproject.toml` carries no Squiddy dependency. `make -C governed` must fail clearly if the pinned commit is not checked out at the configured path.

4. **Catalog and admit the findings note.** `docs/design/AD-030_implementation_findings_001.md` is uncataloged. Run the governed catalog and admit for it. Confirm `seldon verify --strict` reports zero uncataloged governed files after this task's own RESULT file is also cataloged (run the admit twice if needed: once for the note, once for the RESULT after writing it).

5. **Governed sync and edge check.** `seldon governed sync`. Confirm the findings note's Document node holds exactly 9 Ruling nodes (R11 to R19), an `EXTENDS` edge to the AD-030 Document, and `DEPENDS_ON` edges to both RESULT Documents. Confirm the `supersedes` relationships implied by R13 and R17 exist as `SUPERSEDES` edges from the new Ruling to the AD-030 Ruling it replaces (R13 → section 4 text is prose, so R13 supersedes nothing at Ruling granularity; R17 → AD-030-R10). If the recipe cannot recover a `supersedes` edge lexically from a "Supersedes …" clause inside a ruling paragraph, write the one R17 → R10 edge via `seldon link create` and record in the RESULT that lexical recovery of in-paragraph supersession is a gap.

6. **Count verification (AD-030-R18).** Run `seldon result verify` on all 13 Results registered by the ingest task. Every count will have moved (Ruling count down from step 1, Document count up from steps 4 and this RESULT). Follow AD-028 stale handling; the verified set at end of task must reflect the post-R16 graph. Register the final set. Every registered number in this RESULT file must be a `{{result:NAME:value}}` reference or be marked as a pre-verification figure.

7. **CONSTRAINED_BY check.** Query the graph for `CONSTRAINED_BY` edges from the ResearchTask registered for this file. The registration of this file was the first to pass through the R9 gate; report which Rulings it was constrained by and whether the match set is sensible. If zero edges, the gate wrote nothing at registration and that is a defect to fix in this task.

8. Full suite via `python -m dotenv -f .env run -- python -m pytest tests/ -v`. `seldon verify --strict` exit 0. Squiddy suite green if any Squiddy file changed.

## Success Contract

| Deliverable | Verification | Expected |
|---|---|---|
| R16 patterns | `MATCH (d {artifact_type:'Document', name:'AD-030'})-[:CONTAINS]->(r {artifact_type:'Ruling'}) RETURN count(r)` | 10 |
| Findings note admitted | same query with `name` for the findings note | 9 |
| Extends edge | `MATCH (a {artifact_type:'Document'})-[:EXTENDS]->(b {artifact_type:'Document', name:'AD-030'}) RETURN a.path` | includes `AD-030_implementation_findings_001.md` |
| Actor gate | test: unknown `created_by` value is gated | passes |
| Squiddy pin | `pyproject.toml` grep for squiddy | empty; pin present under `governed/` |
| Counts | `MATCH (r {artifact_type:'Result'}) WHERE r.name STARTS WITH 'governed_' RETURN r.name, r.state` | all `verified` |
| Uncataloged | `seldon verify --strict` | exit 0, zero uncataloged |
| Gate wrote edges | `CONSTRAINED_BY` count from this task's ResearchTask | > 0 |

## Scope boundaries

- Do not edit `AD-030_governed_documents_as_graph_content.md` or `AD-030_implementation_findings_001.md`. Findings go in the RESULT.
- Do not relax DI-005. No Neo4j projection into any `seldon-*` database from Squiddy.
- Zero model calls.
- Arnold corpus is out of scope.
- Do not introduce a second closeout term; `seldon handoff` and `seldon closeout` stay distinct.
