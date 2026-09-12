# ADDENDUM 1 to cc_tasks/2026-09-12_ad030_findings_reconcile.md

**Date:** 2026-09-12
**Amends:** Step 7 (CONSTRAINED_BY check)

The task file was registered as ResearchTask `eb359760` via the `seldon_cc_register` MCP tool from a Claude Desktop session whose `seldon-mcp` server process was started before the ingest task merged. That process does not expose `seldon_handoff` and its `seldon_cc_register` returned no ruling matches and wrote zero `CONSTRAINED_BY` edges. Zero edges on `eb359760` is therefore evidence of a stale server process, not of a gate defect.

Replace step 7 with:

7a. Test the gate through the CLI: `seldon cc register` on a throwaway fixture task file that references `AD-030` and mentions "per-set RPE" against the live graph. Confirm it returns rulings and writes `CONSTRAINED_BY` edges. Delete the fixture registration afterwards (withdraw the task with reason "gate fixture").

7b. Backfill `eb359760`: run the gate's matching over `cc_tasks/2026-09-12_ad030_findings_reconcile.md` and write the resulting `CONSTRAINED_BY` edges for the existing task node. Do not re-register (duplicate task). Report the matched rulings in the RESULT.

7c. Only if 7a shows the CLI path also writes zero edges is there a defect; fix it in this task.

Success contract row "Gate wrote edges" now reads: `CONSTRAINED_BY` count from `eb359760` after 7b > 0, and 7a fixture returned at least one ruling.
