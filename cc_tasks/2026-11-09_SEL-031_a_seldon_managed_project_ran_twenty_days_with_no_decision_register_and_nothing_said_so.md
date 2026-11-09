# SEL-031: a Seldon-managed project ran twenty days, 143 tasks and seventeen design notes with no decision register declared, and `seldon init`, `seldon go` and `seldon verify` never said so

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-09
**Reporter:** Desktop session (hazbrief-mcp), from the operator's review of 2026-11-09.

## What was observed

1. hazbrief-mcp's `seldon.yaml` was created 2026-10-20 by `seldon init` (`project.template: blank`). It declares `prior_art`, `dispatch`, `recall`, `environment`, `desktop_commit`, `handoff`. It declares no `decisions:` block. `seldon_decision_list` on the project returns "this project declares no decision register (seldon.yaml `decisions:`)".
2. The file itself names the gap twice, as a reason for other settings (`dispatch.stations` comment: "hazbrief declares no `decisions:` block"; `recall.served.graphs` comment, the same), and no Issue or filing was ever made of it.
3. In twenty days: 143 HB tasks, seventeen DN design notes with addenda, 673 artifacts. Every ruling was written into a design note or stayed in a Desktop chat. Rulings of the second kind have no record anywhere: on 2026-11-09 the operator asked where the brief's basemap decision (Google Maps JS API with an OSM fallback; Google traffic kept out of the submitted repository on licensing and the GSA scope clause, 2026-10-25) was recorded, and the Desktop found it only by searching chat transcripts. The operator's words: "it was vibe chatted and not captured... that's the exact kind of shit that fucks up the state fidelity validity."
4. `seldon go` has reported the project's state on every session since 2026-10-20 (open tasks, chains, stale artifacts, provenance, documentation percentage, system properties) and never reported the absence of a register. `seldon verify`'s eleven checks do not include it.
5. AD-033 section 1 measured the failure this reproduces: "A decision has no record: no stand-alone statement, no status, no declared supersession, no consumer." The register was built to stop it, and a project can run under Seldon without it.

## What hazbrief-mcp wants to know back

- Whether a `decisions:` register is meant to be optional per project. If it is, why, given AD-033 section 1; if it is not, `seldon init` and `seldon project new` created a project without one and said nothing.
- Whether `seldon go` or `seldon verify` should refuse, or at least warn on, a project with no register, the way the dispatcher's c7 refuses a dirty tree.
- What the supported route is for a project adding a register after the fact: which keys `decisions:` needs, whether `seldon decision project` can backfill records whose source is a design note or a chat transcript (a URL and a date, no sha256 of a repository file), and how `operator_stated` records cite a chat.

## Evidence

- hazbrief-mcp `seldon.yaml` at `ce4442d59f9e` (the file, its two comments naming the gap).
- `seldon_decision_list(project_dir=/Users/brock/GitHub/hazbrief-mcp)`, 2026-11-09, the refusal quoted above.
- hazbrief-mcp `docs/design/` (seventeen DN notes as the de facto register); the 2026-10-25 chat "Haz Brief project and social sharing" (claude.ai/chat/ac57d27a-5177-4555-abf2-f66fa6f04bd8) for the Google decision.
- seldon `docs/design/AD-033_decision_register.md` section 1.
