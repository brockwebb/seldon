# ADDENDUM 1 to cc_tasks/2026-09-12_ad030_names_supersession_reingest.md

**Date:** 2026-09-12
**Amends:** step 5 (R16 readings) and step 6 (constraint backfill). Step 6 must not run before the fix below.

## Defect observed at registration

This task file was registered as `85b26c9e` through `seldon_cc_register` from a freshly restarted MCP server. The gate wrote 11 `CONSTRAINED_BY` edges. Verified against the graph: **9 of the 11 targets are `retired` Rulings** (two `AD-030-R10` mentions inside cc_task and RESULT files, three RESULT section headings, three cc_task prohibitions from 2026-09-04 and 2026-09-07, one AD-029 addendum heading). Only 2 targets are `admitted` (AD-030-R10, AD-030-R14).

Reconcile RESULT G1 states `read_rulings` excludes `retired` and `superseded` by default. The register path is not using that default, or is reading state from a property the retire pass did not set. Either way the gate as shipped constrains new tasks by obligations no document imposes, and `seldon cc constrain --all` would replicate that across 58 tasks.

## Amendment to step 5

5a. Find why the MCP register path (and check the CLI path and `seldon cc constrain`) matched retired rulings. Fix so every gate path reads only binding rulings. Add a test that registers a fixture against a graph containing a retired ruling whose text matches strongly and asserts zero edges to it.

5b. Remove the 9 `CONSTRAINED_BY` edges from `85b26c9e` to retired rulings. Keep the 2 admitted ones. Re-run the gate over this task file and report the resulting set.

5c. One of the retired matches is a real ruling lost by R16: `docs/design/AD-029_task_precedence.md` heading `# Addendum 029-A: Seldon never reads a relationship by name alone`. Under AD-030-R23 an identifier that opens a heading and is terminated by `:` is a label. `Addendum NNN-X:` is a ruling ID form this repo already uses. Add it to the label patterns, re-ingest AD-029 via the step 1 path, confirm that ruling returns to `admitted` and that no cc_task or RESULT file gains a ruling from the change. Report the Ruling count delta.

## Amendment to step 6

Run only after 5a and 5b are green. Add to the dry-run review: count of proposed edges whose target is not `admitted`, expected 0.

Success contract adds: `MATCH (:ResearchTask)-[:CONSTRAINED_BY]->(r) WHERE coalesce(r.state,'') <> 'admitted' RETURN count(*)` = 0.
