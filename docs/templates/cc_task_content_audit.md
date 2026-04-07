# CC Task: Content Audit — [SECTION/CHAPTER NAME]

**Date:** [DATE]
**Project:** [PROJECT NAME]
**Reference:** AD-019, Content Audit workflow
**Section:** [PATH TO FILE]

---

## Instructions

1. Read `seldon/docs/agents/auditor_prompt.md` for the full auditor protocol.
2. Run `seldon ontology list --verbose` to get the project's canonical terminology.
3. Read the target file: `[PATH TO FILE]`
4. Read `bibliography.md` or equivalent for existing citation context.
5. Determine `{{RUN_DIR}}`: check `ls -d audits/run-*/` and create the next run directory: `mkdir -p audits/run-{NNN}_{YYYY-MM-DD}`. All output goes here — never to `audits/` root.
6. Execute the audit per the auditor prompt. Output YAML to `{{RUN_DIR}}/[filename]_content_audit.yaml`.
7. Run `seldon paper impact [SECTION_ARTIFACT_ID]` to understand this section's blast radius in the graph.
8. Extract all `citation_gap` findings into a Perplexity verification file at `{{RUN_DIR}}/[filename]_perplexity_queries.md`.
9. For each entry in `cascading_audit_tasks` in the output YAML: create a ResearchTask artifact via `seldon task create` with description referencing the source finding, the target section, and the audit type needed.
   Example: `seldon task create --description "Audit [target_section]: [audit_type] — triggered by [source finding] in [this section]. Reason: [reason]"`
10. Write `{{RUN_DIR}}/run_manifest.yaml` after all gates complete (see auditor.md Step 0 for schema).

## Output Files

- `{{RUN_DIR}}/[filename]_content_audit.yaml` — structured findings
- `{{RUN_DIR}}/[filename]_perplexity_queries.md` — verification queries for citation gaps
- `{{RUN_DIR}}/run_manifest.yaml` — run metadata

## Do NOT

- Edit the audited file
- Create Issue artifacts (that's Phase 2 automation)
- Run seldon paper audit (that's AD-016 prose QC, separate concern)

## Success Contract (Optional)

For complex audit runs spanning multiple chapters or requiring coordination across multiple agents, fill out a success contract before execution. See `docs/templates/cc_task_contract.md` for the template. Simple single-chapter audits do not need a contract.
