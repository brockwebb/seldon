# Filing review findings as Issues (factory F-010)

**Governing:** factory F-010 (a review finding is an Issue, traced both ways) and F-011 (`found_in` cross-repository
links), `factory/docs/architecture.md` section 5; F-002 (a defect is filed where it is fixed).
**Built by:** SEL-021. **Code:** `seldon/core/review_findings.py`, `seldon issue create|update|orphans`,
`seldon_issue_create|update|orphans` (seldon-mcp), the `**Found in:**` header (`seldon/core/dispatch.py`
`static_checks`).
**Prior art:** requirements traceability. Gotel and Finkelstein 1994 (pre- and post-specification trace), DO-178C
bidirectional trace and ISO/IEC/IEEE 29148:2018 set the two-way rule. A disposition that is not a fix must carry its
justification, as a SARIF 2.1.0 suppression does and as IEEE 1044-2009's anomaly disposition does.

## The rule

Each finding of a code or design review becomes one Issue in the graph of the repository that will fix it. The
review file stays where it was written, usually `factory/reviews/`. The Issue points back to the review through
`found_in` and forward through its edges:

| What | Where it lives |
|---|---|
| where the finding was raised | `found_in`: `<repo>:<path>#<finding id>` (`factory:reviews/squiddy_code_review_max_findings.md#3`) |
| how bad the review said it was | `severity`, the review's own words |
| the task that fixes it | `REMEDIATED_BY` -> ResearchTask |
| the test that shows the fix holds | `VERIFIED_BY` -> a Script standing for one pytest node id (`tests/test_x.py::test_y`) |
| a decision the outcome altered | `CHANGES` -> a register record (`squiddy:R-112`) or an ArchitecturalDecision |
| a finding not fixed | `disposition` `rejected`, `duplicate` or `wont_fix`, plus `disposition_evidence` saying why and where that is recorded |

## Filing, step by step (coordinator)

1. **File each finding when the review lands, before any fix task exists.** Use one Issue per finding id:
   ```
   seldon issue create --type review_finding --detection review --target code \
     --importance high --urgency medium --name "SQ review #3" \
     --description "<the finding, one or two sentences>" \
     --found-in factory:reviews/squiddy_code_review_max_findings.md#3 --severity "P1"
   ```
   In seldon-mcp, call `seldon_issue_create` with the same fields. A `review_finding` Issue without `found_in` is
   refused.
2. **The fix task names the finding.** Put `**Found in:** <the same found_in>` in its header block. Registration
   records the value on the ResearchTask. An unparsable value is refused with the grammar quoted.
3. **When the fix merges, link it.** Use `seldon issue update <issue> --disposition fixed --remediated-by <task>
   --verified-by tests/test_x.py::test_y [--changes <decision id>]`. The test file must exist in this repository.
   The node id is recorded as given. Every link is resolved before anything is written, and all of them go in one
   append.
4. **When a finding is rejected, say why.** Use `seldon issue update <issue> --disposition rejected
   --disposition-evidence "<reason>; <RESULT section or decision id>"`. A disposition other than `fixed` without
   evidence is refused.
5. **Check.** `seldon issue orphans` lists every review finding that has neither a completed (or verified) fix task
   plus a test, nor a non-`fixed` disposition with evidence. It exits 1 while any finding is listed. Run it before
   reporting a review closed. Factory plan stage 3 is passed when it shows 0 in squiddy and hazbrief-mcp.

## What this is not

- Ordinary bugs and feature requests found outside a review are still CC tasks, not Issues.
- The Issue state machine (`open` -> `resolved` -> `verified`) is unchanged and independent of the trace. Moving a
  fixed finding to `resolved` is good hygiene. `orphans` reads the edges and the disposition, not the state.
