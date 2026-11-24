# Filing from hazbrief-mcp: a Part's bare check line is not read, a blocked merge was completed with no gate, and hazbrief's queue waited on seldon's lease

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-24 12:15 EST, Desktop session hz-25. Items 1 and 2 are HB-224's "For seldon" section, relayed as that task asked.

## What hazbrief observed

1. **A Part's bare `check:` line is not read, so the merge round runs the full gate.** HB-217 relays SEL-042: "To make the session's gate the evidence instead, give each Part a `check:` line." HB-221 and HB-222 each carry `check: uv run pytest ...` directly under every `## Part X:` heading. The Stop gate recorded `"checks": []` with `"section_found": true` for every Part, `dispatch_finished` recorded `"checks_run": 0`, and the round ran `gate_command` as its evidence gate (36:18 red for HB-221, 52:54 green for HB-222). HB-223 to HB-227 are written the same way. Registration did not refuse any of these files as `criterion_unmarked`.
2. **A merge the round blocked was completed with no gate on the merged tree, and its successor was released on it.** The round blocked HB-221 (`regate_red`). A person regenerated one file and merged by hand (`c8bc9fb8`, 2026-11-23 20:47:51Z). `seldon cc complete` marked it completed, and the OODA released HB-222 on that completion. The record holds no gate evidence for the tree that reached main. HB-223's first full gate on 2026-11-24 found main red.
3. **Hazbrief's queue waited on seldon's lease for about 100 minutes.** HB-224 completed at 15:27:33Z on 2026-11-24. HB-226 and HB-227 were ready. Every hazbrief pass from then until 17:01:00Z printed `refused: environment_in_flight: a dispatcher holds a lease on seldon, which this project's environment names`. HB-226 launched at 17:06:10Z, after seldon's SEL-045 blocked at 17:03:21Z. Nothing told a person that hazbrief was waiting.
4. **A hold on a governing note also waited silently.** On 2026-11-24 from 07:46Z to 09:20Z hazbrief's HB-225 was refused on every pass, `governing_unverified: c14`, for a note committed by `seldon_commit_governed` the night before with no verdict. Desktop found it only by reading `seldon go`.

## Evidence

- `hazbrief-mcp/docs/evidence/hb224/timeline.tsv` and `README.md`; `hazbrief-mcp/cc_tasks/2026-11-24_HB-224_where_the_hours_of_hb221_and_hb222_went_RESULT.md`, section "For seldon", with the event and log lines for items 1 and 2.
- `hazbrief-mcp/logs/seldon_dispatch.log`, the passes from 2026-11-24T15:30Z to 17:06Z, for item 3.

## What hazbrief wants to know back

1. In what form a task's Part must state its check so the Stop gate reads it, and whether the form HB-217 relayed is meant to work.
2. Whether `seldon cc complete` on a task the round blocked is meant to complete it with no gate evidence.
3. Whether a consumer's dispatcher is meant to wait for the whole of a producer's task, gate included, and how a person learns it is waiting.
