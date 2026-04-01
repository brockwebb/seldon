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
6. Extract all `citation_gap` findings into a Perplexity verification file at `audits/[filename]_perplexity_queries.md`.

## Output Files

- `audits/[filename]_content_audit.yaml` — structured findings
- `audits/[filename]_perplexity_queries.md` — verification queries for citation gaps

## Do NOT

- Edit the audited file
- Create Issue artifacts (that's Phase 2 automation)
- Run seldon paper audit (that's AD-016 prose QC, separate concern)
