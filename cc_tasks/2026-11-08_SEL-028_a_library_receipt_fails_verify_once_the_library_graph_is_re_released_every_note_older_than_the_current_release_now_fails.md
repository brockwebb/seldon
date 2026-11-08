# SEL-028: a library receipt fails `prior-art verify` with `release_unavailable` once the library graph is re-released, so every design note older than the current release now fails, and no addendum to it can carry a passing verdict

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-08
**Reporter:** Desktop session (hazbrief-mcp).

## What was observed

1. `seldon_prior_art_verify` on `docs/design/2026-11-04_DN-019_the_brief_as_a_live_view_what_is_on_by_default_and_what_the_held_screens_teach.md` (with its new ADDENDUM-01) returned FAIL, verdict event `ea01ac75ed6043c8b8a2324d66d0f413`. The one failing line is the base note's library receipt at line 62: `release_unavailable: release sha256:7b72aaa89fe0... cannot be rebuilt: no commit of /Users/brock/GitHub/squiddy/graphs/library/exports/EXPORT_VERSIONS.md carries 7b72aaa89fe005d3`. Every internal receipt and the addendum's own library receipt (against release `library_graph_20261106_sq125_c`, sha256 `bbd841d3...`) pass.
2. The base note was written 2026-11-04 against the library release of that day. HB-125 (hazbrief-mcp, 2026-11-07/08) extracted 69 works and produced a new library release; the old export is no longer recorded in `EXPORT_VERSIONS.md`, so the receipt's release cannot be rebuilt.
3. Consequence: every note whose receipts predate the current release fails verify when touched (an addendum, a correction), and by AD-036-R4 a failing note cannot be committed with a verdict and a task it governs is held at registration. `seldon_commit_governed` did commit the addendum (`e7d7fef5b4c6`) without the draft marker, which is inconsistent with the FAIL verdict just recorded; either the gate did not re-check or the verdict event, uncommitted because the lease is held, was not read.

## What hazbrief-mcp wants to know back

- Whether `EXPORT_VERSIONS.md` is meant to carry every release ever produced (then HB-125's release step in hazbrief-mcp or the squiddy export dropped a row, and the fix is in squiddy) or whether verify should accept a receipt whose release is superseded by a later one that contains the same rows (then the check is in seldon and a receipt needs a `superseded_by` resolution rather than a rebuild).
- Whether a verify FAIL on a base note's stale receipt should block an addendum whose own receipts pass. The addendum's claims rest on its receipts, not the base note's.
- Why the commit gate accepted the addendum after a FAIL verdict in the same session.

## Evidence

- hazbrief-mcp `state/prior_art_verdicts.jsonl`, event `ea01ac75ed6043c8b8a2324d66d0f413`, 2026-11-08 ~17:50Z.
- hazbrief-mcp commit `e7d7fef5b4c6`.
- squiddy `graphs/library/exports/EXPORT_VERSIONS.md` at HEAD, which lacks `7b72aaa89fe005d3`.
