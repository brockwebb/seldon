# Template: Agent Team Content Audit

**Reference:** AD-019, Agent Team Audit Pattern
**Subagent definitions required:** `.claude/agents/auditor.md`, `.claude/agents/cascade-checker.md`

---

## Prerequisites

1. Subagent definitions in project's `.claude/agents/`:
   - `auditor.md` — full content auditor
   - `cascade-checker.md` — lightweight cascade verifier
2. Agent teams enabled in CC settings:
   ```json
   { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
   ```
3. Project has Seldon initialized (`seldon.yaml` exists)
4. `audits/` directory exists at project root

## Invocation

Tell the CC lead session:

```
Run a content audit on [TARGET_FILE] using the agent team pattern.

1. Use the auditor agent protocol to audit the chapter. Write YAML output to
   audits/[filename]_content_audit.yaml and Perplexity queries to
   audits/[filename]_perplexity_queries.md.

2. After the audit, read the cascading_audit_tasks section of the YAML output.
   Group tasks by target chapter.

3. For each unique target chapter, spawn a cascade-checker teammate with a prompt
   containing: the target file path, the specific finding(s) to check, and the
   audit type. Cap at 5 concurrent teammates.

4. Wait for all teammates to report back. Collect their cascade_check YAML.

5. For each "confirmed" result: append to audits/[filename]_cascade_results.yaml
   For each "needs_full_audit" result: note for follow-up (separate audit run)
   For each "clear" result: no action

6. Print a summary of the audit + cascade results to terminal.

7. Clean up the team.
```

## Workflow Detail

### Phase 1: Lead Audits Target

The lead session runs the full auditor protocol:
- Loads ontology context via `seldon ontology list --verbose`
- Reads the target file
- Reads `references.bib` or bibliography
- Produces structured YAML findings
- Extracts Perplexity verification queries

### Phase 2: Lead Spawns Cascade Checkers

For each unique target chapter in `cascading_audit_tasks`:

```
Spawn a teammate using the cascade-checker agent type with the prompt:

"Check [target_file] for these cross-section impacts from [source_file]:

1. [audit_type]: [reason]
   Triggered by: [triggered_by]
   Priority: [priority]

Read [target_file]. Produce cascade_check YAML for each finding.
Report results and shut down."
```

Batch multiple findings for the same chapter into one teammate.

### Phase 3: Lead Collects and Synthesizes

- Wait for all teammates to finish
- Collect cascade_check outputs
- Write confirmed findings to `audits/[filename]_cascade_results.yaml`
- Print terminal summary

### Phase 4: Clean Up

Lead cleans up the team. All teammates should have self-terminated.

## Token Budget

| Component | Estimated tokens |
|-----------|-----------------|
| Lead audit (one chapter) | ~20-30K |
| Each cascade checker | ~5-10K |
| 6 cascade targets | ~30-60K |
| **Total** | **~50-90K** |

Compare: one session reading all chapters sequentially would be ~100-150K+ with high context pressure and degraded quality on later chapters.

## Do NOT

- Run cascade checkers on chapters not in `cascading_audit_tasks`
- Let cascade checkers expand scope beyond their assigned finding
- Run full audits from cascade checker teammates
- Edit any chapter files — audit-only workflow
- Create Issue artifacts in the graph (future: `seldon audit ingest`)

## Success Contract (Optional)

For complex audit runs spanning multiple chapters or requiring coordination across multiple agents, fill out a success contract before execution. See `docs/templates/cc_task_contract.md` for the template. Simple single-chapter audits do not need a contract.
