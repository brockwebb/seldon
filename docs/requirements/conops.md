# Seldon — Concept of Operations

## Actors

- **Researcher** (Brock) — domain expert, writes and reviews
- **Claude** (AI assistant) — drafts, searches, assembles, cites
- **ANTS** — tracks relationships between research artifacts
- **Wintermute** — stores and retrieves knowledge entities

## Operational Workflow

### Starting a Research Session
1. Load briefing (Wintermute context + ANTS state + last handoff)
2. Review open questions, unresolved findings, draft status
3. Set session goals

### During a Session
1. Use lab notebook template for observations, findings, decisions
2. Tag every entry with keyword taxonomy
3. Cite sources in APA 7th using references.bib
4. Cross-reference related entries via `[[YYYY-MM-DD_slug]]` links

### Ending a Session
1. Write handoff document (what was done, what's next, open questions)
2. Update bibliography if new sources were used
3. Commit to git

### Producing Output
1. Assemble report sections from lab notebook entries and findings
2. Generate bibliography from references.bib
3. Review structural coherence
4. Export to target format (markdown → docx/pdf as needed)

## Session Continuity Model

Each session is assumed to start with no memory of prior sessions.
All context must be recoverable from:
- `handoffs/` — narrative session notes
- `templates/` — structural consistency
- `docs/references/references.bib` — citation authority
- Git history — temporal record
