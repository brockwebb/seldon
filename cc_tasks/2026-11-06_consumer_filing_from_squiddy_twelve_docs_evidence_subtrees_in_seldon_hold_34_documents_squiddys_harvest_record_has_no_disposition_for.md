# Consumer filing from squiddy: twelve `docs/evidence/*` subtrees in seldon hold 34 documents that squiddy's harvest record has no disposition for, so squiddy's conformance item 15 is red on main, and the record is out of date every time a seldon task adds evidence

**Repo:** seldon. **Date:** 2026-11-06. **Authored by:** a Desktop session in squiddy (SQ-13), from squiddy SQ-114R's RESULT section 9 (`cc_tasks/2026-11-05_SQ-114R_library_release_unblocked_at_item_19_and_parts_b_and_c_run_RESULT.md`), filed into seldon's queue under AD-036-R12 as a report of what a consumer measured. No candidacy headers, not a dispatcher candidate; it registers when SEL-023 Part A lands, and until then seldon's Desktop registers it. This filing proposes no fix; the seldon thread decides what, if anything, changes.
**Evidence:** squiddy `squiddy/conformance.py` `harvest_walk_complete` (item 15, scope code, level error; source L-001 Part A, DN-020 R-93, DI-207 to DI-209) and `harvest_findings`; squiddy `squiddy/conformance.yaml` `harvest_walk` (record `docs/inherited/harvest_walk.yaml`, eleven document extensions); squiddy `docs/inherited/harvest_walk.yaml` at `af8e40e9` (2026-10-22, its last change); seldon main at `64cbbd6` (2026-11-06 09:25 local); the walk below, re-run from the Desktop on 2026-11-06 against both; squiddy SQ-114R RESULT section 9; seldon SEL-006 (2026-10-15), which found the same gate red on main for `docs/evidence/disp_c7` and dispositioned it; squiddy SQ-010 Part 1 (R-184), which moved this gate to the `integrity` tier because its input is state outside squiddy's tree.

## What the consumer measured

1. **The gate's finding, re-run today.** `harvest_findings` over the record and seldon's `docs/` tree: 48 subtrees hold documents, 36 are dispositioned, 12 are not, 0 rows are stale. The twelve, with the gate's own wording:

   ```
   seldon: docs/evidence/disp001r (2 document(s)) has no disposition
   seldon: docs/evidence/friction002 (2 document(s)) has no disposition
   seldon: docs/evidence/prune001 (8 document(s)) has no disposition
   seldon: docs/evidence/prune002 (2 document(s)) has no disposition
   seldon: docs/evidence/recall002r (1 document(s)) has no disposition
   seldon: docs/evidence/sec001/applied (2 document(s)) has no disposition
   seldon: docs/evidence/sec001/dry_run (2 document(s)) has no disposition
   seldon: docs/evidence/sel009 (1 document(s)) has no disposition
   seldon: docs/evidence/sel012 (2 document(s)) has no disposition
   seldon: docs/evidence/sel014r (3 document(s)) has no disposition
   seldon: docs/evidence/sel015 (8 document(s)) has no disposition
   seldon: docs/evidence/std001 (1 document(s)) has no disposition
   ```
   34 documents. Every one is under `docs/evidence/`, and every directory name is a seldon task id. All twelve post-date the record's last change (2026-10-22) or were missed by it.

2. **What the record already says about such directories.** Each `docs/evidence/*` row it holds is `declined` with a reason of the form "a measurement of one task, whose decisions are <the register records>" (`evidence/sq022`, `evidence/sel006`, `evidence/disp_c7`). SEL-006 wrote the `disp_c7` row on 2026-10-15 after finding this gate red on main for it. The pattern has repeated: a seldon task writes evidence, squiddy's record does not know, the gate is red until a squiddy task declines the row by hand.

3. **Where it bites.** The gate is `error` level in squiddy's code scope, deselected from the recorded kit pass (SQ-010 R-184) because its input is outside squiddy's tree, so it does not block squiddy's merges. It fails whenever the full suite runs where seldon's checkout exists: SQ-114R's full suite (2,821 passed, 5 failed) counted it among the five, and the session could not tell by reading the failure whether a document had been missed or a directory had merely grown. The signal is noise until someone reads the paths.

4. **What the walk does not see.** Three other repositories in the record (`ai-readiness-kg`, `icsp_notebook`, `arnold`) and the `sfv-paper` root were not reachable from the Desktop's mount, so their state is unmeasured here; the twelve findings above are seldon's alone and match SQ-114R's list.

## What the consumer wants to know back

Whether a seldon task's `docs/evidence/<task>/` directory is ever harvest material for a consumer (a document whose decisions a consumer should inherit), or is by construction "a measurement of one task, whose decisions are its register records", in which case squiddy would decline `docs/evidence` once, `recursive: true`, and the gate would stop re-reporting each new task. The record's `recursive` mechanism exists for exactly that ("one disposition for a whole tree; stated, never implied"), and squiddy will not write that row on its own: the statement that evidence directories carry no decisions a consumer inherits is seldon's to make.
