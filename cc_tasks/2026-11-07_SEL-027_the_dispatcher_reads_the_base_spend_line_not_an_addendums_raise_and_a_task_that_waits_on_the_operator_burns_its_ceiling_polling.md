# SEL-027: the dispatcher's `spend_ceiling` reads the task file's base Spend line and not an addendum's raise; and a Part that waits on the operator inside a headless session spends its ceiling on polling

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-07
**Reporter:** Desktop session (hazbrief-mcp), from the OODA of HB-115.

## What was observed

1. HB-115 (`cc_tasks/2026-11-04_HB-115_the_display_review_is_served_five_briefs_over_http_two_questions_recorded.md`) carries `**Spend:** ... 600,000 ...`. Its ADDENDUM-01 section 4 raised that line to 1,200,000. The dispatcher's andon halted the run at 942,515 tokens against a ceiling of 720,000, which is 1.2 times the base line. The addendum's raise was not read (HB-115 RESULT, Outcome and For Desktop item 2).
2. HB-115 Part B was a 24-hour wait for the operator's answers on a served page, polled once a minute in 9-minute slices from a headless session. The polling is what spent the tokens; 0 of 5 answers had arrived at the halt (7.4 h in). The task shape is the consumer's own defect, but the dispatcher has no form for "wait on an external input" that does not consume the session's ceiling.

## Evidence

- hazbrief-mcp `cc_tasks/2026-11-04_HB-115_..._RESULT.md`, sections Outcome, 3 and 7; `docs/evidence/hb115/served.json` (`stopped_because`).
- The addendum: `cc_tasks/2026-11-04_HB-115_..._ADDENDUM_01_the_first_screen_is_true_before_it_is_reviewed_and_the_operator_cue_block.md`, section 4.

## What hazbrief-mcp wants to know back

- Whether an addendum may raise a task's Spend at all, and if so where the dispatcher reads it (the registered hash is the base file's; an addendum is a separate file). If not, the convention should say a Spend raise is a re-filing (`R` suffix), and `seldon_cc_register` should refuse an addendum that carries a `**Spend:**` line.
- Whether the dispatcher can offer a wait form: a task completes a Part, declares `waits_on: <path or predicate>`, releases its lease and session, and is relaunched by the standing dispatcher when the predicate holds, so an operator input costs no tokens while it is awaited. Until then hazbrief-mcp will split such Parts into their own tasks, launched by hand once the input exists.
