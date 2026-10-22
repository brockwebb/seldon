# SEL-007: `seldon task create --depends-on` is atomic, or it creates nothing

**Status:** proposed
**Author:** Desktop session (hazbrief), 2026-10-21
**Spend:** no model call. **Network:** none.
**Governed by:** AD-030 (task registration and the event ledger). If the ledger's write discipline lives in another AD, cite that one in the RESULT and say so.

## The defect

`hazbrief-mcp/cc_tasks/2026-10-21_HB-01e_register_operator_downloads_RESULT.md` section 10a: `seldon task create --depends-on <id>` wrote the `artifact_created` event for the new task, then refused the link ("'ResearchTask' cannot target a 'depends_on' relationship"), and exited with an error that read as if nothing had been created. The orphan (`7b76e2c3`) duplicated the task created next without the option (`740b40c3`) and had to be superseded by hand.

Two faults: the validation runs after the first write, and the error text does not say an artifact was created.

## Steps

1. Test first: `task create` with an illegal `--depends-on` target writes no event and creates no artifact; with a legal one it writes both events or neither (validate every edge before the first write; a single ledger append of all lines).
2. The error names the illegal relationship and the legal targets for it. If the relationship the operator wanted is `precedes` on a ResearchTask (it was), say so in the error.
3. Any command that writes more than one event line gets the same treatment; list them in the RESULT with a test each, or say why one is exempt.
4. Gate; commit; push.

## Deliverables

Code, tests, `cc_tasks/2026-10-21_SEL-007_task_create_depends_on_is_atomic_RESULT.md`.
