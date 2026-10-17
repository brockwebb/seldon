# PRUNE-001: a weekly prune stage closes issues that are already fixed, re-dates or withdraws stale FUTURE proposals, and re-measures each repository's exit bar

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/squiddy`, `/Users/brock/GitHub/arnold`, `/Users/brock/GitHub/ai-readiness-kg`. L4: commit, merge, push in every repo touched.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** squiddy CLAUDE.md ("Maintenance is in scope and is scheduled stages with gates ... never unbounded agents. The weekly sweep is the template"); AD-038-R6 (toil measure). Prior art read, not searched: L. Weathers, "SHIP" (Medium, 2026-07-01): deprecation as a scheduled, celebrated event; a knowledge base that never lets anything die cannot tell the living from the dead. No new ruling.
**After:** c48b3fd6
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: a read-mostly sweep over four graphs plus one launchd lane.
**Parts:** A 0.6, B 0.4.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: squiddy carries the open issues to prune | check: `test -f /Users/brock/GitHub/squiddy/seldon_events.jsonl`

Glob and read every sibling `*PRUNE-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Token ceiling 0.48M. Zero model calls. The sweep never deletes: it closes, re-dates, withdraws with reason, or leaves alone.

## Part A: the first prune, by hand-written rule

1. For each of the four repositories: list open Issues whose own text says fixed, resolved, closed or superseded, or whose named commit is on main. Resolve each with the commit as the reason. Record the list in `docs/evidence/prune001/<repo>_issues.md`.
2. List `proposed` tasks named FUTURE older than 60 days with no edge from an open task. Re-date the ones whose trigger is still plausible (one line why) and withdraw the rest with reason `stale 60 days, no trigger seen`.
3. Re-run each repository's R-186 exit measurement where one exists and append the row.
4. Report the counts before and after per repository.

Acceptance:
- `check: test -f docs/evidence/prune001/squiddy_issues.md`

## Part B: the lane

1. A weekly launchd lane, Sunday 03:30 local, runs the same sweep under `seldon prune` with the Part A rules in `seldon.yaml` (`prune.stale_days`, `prune.fixed_markers`). It writes `prune_pass` records and a STUCK-style notification only when a count is nonzero.
2. Spend control per DN-042: the lane carries a token cap and stops at 20 percent over.
3. Tests: the fixed-marker rule closes a planted issue; the 60-day rule withdraws a planted proposal and re-dates one with an edge; a run with nothing to do writes one record and no notification.

Acceptance:
- `check: pytest tests/test_prune001.py -q`

## Report

RESULT under 25 lines: counts before and after per repository; the exit rows; the lane's first pass; premises found wrong. Then `seldon verify`, `seldon cc complete`, merge, push.
