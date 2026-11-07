# SEL-026: `seldon_commit_governed` cannot stage the verdict ledger its own commit hook requires beside a verified design note

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-07
**Reporter:** Desktop session (hazbrief-mcp)

## What was observed

1. A Desktop session wrote `docs/design/2026-11-07_DN-022_the_gui_an_interactive_application_with_a_model_in_the_loop_over_the_gathered_state.md` in hazbrief-mcp and ran `seldon_prior_art_verify` on it: PASS, verdict recorded as event `9f8ca68893eb484d996ad8e2798cc739` for sha256 `39b759bd5801...` (ledger `state/prior_art_verdicts.jsonl`, ts 2026-11-07T13:47:36Z).
2. `seldon_commit_governed(paths=[the note])` returned: `REFUSED hook_refused: git_commit_failed: seldon commit gate: 1 finding(s) in the staged files: Prior art: <note>: no prior-art verdict for its current bytes (sha256 39b759bd5801); run seldon prior-art verify <note> (AD-036-R4); then stage the verdict ledger state/prior_art_verdicts.jsonl with the note`.
3. `seldon_commit_governed(paths=[the note, "state/prior_art_verdicts.jsonl"])` returned: `REFUSED outside_roots: state/prior_art_verdicts.jsonl is under none of docs/design/, cc_tasks/, handoffs/, issues/, ontology/; this tool commits only what a Desktop session writes`.

The hook's gate reads the verdict from the staged ledger; the MCP commit tool refuses to stage that ledger. A verified note is therefore uncommittable from a Desktop session through the tool, and the hook's own instruction ("stage the verdict ledger with the note") cannot be followed with the tool it is addressed to.

## Evidence

- hazbrief-mcp `seldon_events.jsonl` and `state/prior_art_verdicts.jsonl`, events at 2026-11-07T13:47Z.
- The two refusal strings above, verbatim.
- The previous note in the same repository, DN-021 (verdict event `58e0bfca697a473eae73881f284c4503`, 2026-11-07T12:44Z), appears in the committed handoff of the same day, so some path committed it; the hazbrief session did not record which. The search receipts of this session also report `prior-art lines in /Users/brock/GitHub/hazbrief-mcp not committed: dirty_before_this_run`, so the ledger was already dirty before DN-022 was written.

## What hazbrief-mcp wants to know back

- Which route a Desktop session should use to commit a verified note: does the tool's root list gain the verdict ledger, does the hook read the verdict from the ledger on disk rather than the index, or is the committing of the ledger a dispatcher sweep the session should wait for?
- Whether `seldon_cc_file` is meant to be exposed by `seldon-mcp`: this session's tool list carries `seldon_cc_register` and `seldon_cc_complete` but no `seldon_cc_file`, so this filing was written through the Filesystem tool and registered with `seldon_cc_register`, against AD-038-R20's instruction.
