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
5. Execute the audit per the auditor prompt. Output YAML to `audits/[filename]_content_audit.yaml`.
6. Run `seldon paper impact [SECTION_ARTIFACT_ID]` to understand this section's blast radius in the graph.
7. Extract all `citation_gap` findings into a Perplexity verification file at `audits/[filename]_perplexity_queries.md`.
8. For each entry in `cascading_audit_tasks` in the output YAML: create a ResearchTask artifact via `seldon task create` with description referencing the source finding, the target section, and the audit type needed.
   Example: `seldon task create --description "Audit [target_section]: [audit_type] — triggered by [source finding] in [this section]. Reason: [reason]"`

## Output Files

- `audits/[filename]_content_audit.yaml` — structured findings
- `audits/[filename]_perplexity_queries.md` — verification queries for citation gaps

## Do NOT

- Edit the audited file
- Create Issue artifacts (that's Phase 2 automation)
- Run seldon paper audit (that's AD-016 prose QC, separate concern)

## Success Contract (Optional)

For complex audit runs spanning multiple chapters or requiring coordination across multiple agents, fill out a success contract before execution. See `docs/templates/cc_task_contract.md` for the template. Simple single-chapter audits do not need a contract.
