# Skill: Research Writing Workflow

## When Working in Seldon

### Lab Notebook Entries
- ALWAYS use the template at `templates/lab_notebook_entry.md`
- ALWAYS include YAML frontmatter with date, type, status, tags
- ALWAYS tag with keywords from the project's taxonomy
- ALWAYS cite sources in APA 7th edition format
- File naming: `YYYY-MM-DD_<descriptive-slug>.md`

### Literature Notes
- ALWAYS use the template at `templates/literature_note.md`
- ALWAYS include the full APA 7th citation
- ALWAYS add the citation to `docs/references/references.bib`
- Include citation_key in frontmatter matching the .bib entry

### Citations
- Standard: APA 7th Edition
- Parenthetical: `(Author, Year)`
- Narrative: `Author (Year)`
- Multiple authors: `(Author1 & Author2, Year)` or `(Author1 et al., Year)`
- Direct quotes: include page number `(Author, Year, p. XX)`
- Canonical bibliography: `docs/references/references.bib`

### Session Protocol
- Start: Read most recent handoff in `handoffs/`
- During: Use templates, tag entries, cite properly
- End: Write handoff to `handoffs/YYYY-MM-DD_<slug>.md`

### Keyword Tags
Use consistent tags. Prefer existing tags over creating new ones.
Check recent entries for established vocabulary before inventing.

### Cross-References
Link between entries using: `[[YYYY-MM-DD_slug]]`
This is a convention, not rendered — it's for grep and human navigation.

### Handoff Documents
Every session that produces work MUST end with a handoff containing:
1. What was accomplished
2. What's next / open items
3. Key decisions made and rationale
4. Any new references added
