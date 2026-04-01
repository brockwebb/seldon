# Audit Output Convention

## Directory: `audits/`

Every Seldon-managed project that runs content audits stores output in an `audits/` directory at the project root. This is a project-level output directory, not a Seldon artifact directory.

## Files

| Pattern | Contents |
|---|---|
| `audits/<filename>_content_audit.yaml` | Structured YAML findings from the content auditor |
| `audits/<filename>_perplexity_queries.md` | Verification queries for citation gaps |

## Lifecycle

1. CC task invokes the auditor protocol on a section/chapter
2. Auditor produces YAML findings → `audits/`
3. (Phase 2) Findings are converted to Issue artifacts via `seldon issue create`
4. Issues are tracked through resolution in the graph
5. Audit YAML files are kept as historical records (not deleted after issue creation)

## Gitignore

`audits/` should generally be committed — the findings are part of the project's quality record. Large projects may choose to gitignore and regenerate on demand.
