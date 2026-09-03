# CC Task: Register Glossary-Ontology Architecture Gap Design Note

**Date:** 2026-04-03
**Repo:** seldon
**Scope:** Graph registration — no code changes

---

## What

The file `seldon/docs/2026-04-03_glossary_ontology_architecture_gap.md` exists on disk but is not registered in the Seldon graph.

## Instructions

```bash
cd /Users/brock/Documents/GitHub/seldon
set -a; source .env; set +a

# Check what type to use
seldon artifact list --type LabNotebookEntry

# Register
seldon artifact create \
  --type LabNotebookEntry \
  --prop name="Glossary-Ontology Architecture Gap" \
  --prop file_path="docs/2026-04-03_glossary_ontology_architecture_gap.md" \
  --prop summary="Design note capturing the gap between project glossaries (flat files) and the shared ontology graph (AD-017). Four options evaluated for glossary-as-projection vs glossary-as-source. Recommends Option B (glossary as source with graph sync) with path to Option C (hybrid). Deferred until verify glossary path fix provides data on gap size." \
  --prop status="open" \
  --prop date="2026-04-03"

# Link to AD-017 — get the AD-017 artifact ID first
seldon artifact list | grep -i "AD-017\|ontology"
# Then:
seldon link create \
  --from <glossary-gap-note-id> \
  --to <AD-017-artifact-id> \
  --type informs
```

## Verification

```bash
seldon link list --from <glossary-gap-note-id>
# Should show informs edge to AD-017
```

## Do NOT

- Modify the design note content
- Create any new commands or artifact types (that's deferred per the design note itself)
