# Filing from factory: 14 things the operator said in seldon's record that no need, decision or task cites

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-27. Written by the factory coordinator, FAC-62 (factory `cc_tasks/2026-11-27_FAC-62_the_489_things_the_operator_said_that_nothing_acts_on_are_each_given_a_place.md`), from FAC-40's extraction (factory `docs/evidence/fac40/unclaimed.md`). This reports what the factory found. How seldon disposes each one is seldon's to decide.

## What the factory found

FAC-40 read 518 documents across the registered repositories with a model and kept every statement of the operator's that resolves word for word to its source lines. It then checked, by code, which of them any stakeholder need, decision record or task of any repository cites (eight consecutive words in common, or the file named with an overlapping line range). 489 are cited by none. The operator's words on why this matters, 2026-11-26: things get discussed, he later finds they were never implemented, it was never clear whether or why not, and they get rediscovered.

These 14 were said in seldon's record, or are about seldon's product (3 commitment, 10 decision, 1 need). The factory disposed the ones about the factory itself; these are yours.

**Read each against its lines before acting on it.** FAC-62 read 40 of the 489 against their sources: all 40 render their lines faithfully, but 6 of the 40 are not his words. Each of the six was Desktop's or a document's text in a document about him: a design note's remedy for a defect he named, a plan's order of work, a handoff's instruction to the next thread, an SRS decision-log entry describing him, a drafted protocol's criteria (`docs/evidence/fac62/sample.md` in factory). Expect about one in seven here to be the same.

## What the factory wants back

For each statement, exactly one of (factory DN-002 and F-034, the rule factory used for its own):

- **restates** a need or decision you hold: add this source to that record;
- **superseded** by a later statement or decision of his: say which;
- **a need nothing holds:** add it to your record with a disposition (built only with what satisfies it, planned only with a task that exists, otherwise deferred with a reason and an end, or undecided);
- **not a need or decision** (an aside, a step already taken, a fact of the moment, or not his words): one line why.

Then a return to factory with the counts by disposition, so that factory's never-built page (`site/never_built.html`) and the next unclaimed count see them. Nothing here asks for a build task.

## The statements

Grouped by subject (FAC-62 Part A: blocked by repository, then single-link TF-IDF cosine at 0.18), each group newest first. Each line: the statement's id, the date of its document, the extractor's type, the source lines, his words as quoted, and the extractor's reading.

### G299: task, run, constrained, nine

- `U-e0d83010` 2026-10-09, decision, `handoffs/2026-10-09_squiddy_split_from_ai_readiness_thread.md#L15`: "run it only when a task is found that a decision should have constrained and did not" (read as: SEL-003 is to be run only when a task turns up that a decision should have constrained but did not.)

### G319: low, instrument, consumer, parked

- `U-a49e2cc7` 2026-10-09, decision, `handoffs/2026-10-09_squiddy_split_from_ai_readiness_thread.md#L15`: "SEL-003 (seldon e60b17fe, ~11M notional) was PARKED by the operator on 2026-10-06 as low value: an instrument test with no consumer this month" (read as: The operator parked SEL-003 as low value, since it is an instrument test with no current consumer.)

### G284: kill, list, phase, synthesis

- `U-aa44a60b` 2026-04-18, commitment, `handoffs/2026-04-18_evolution_burst_closeout.md#L47`: "Kill list (infrastructure + components only — per Addendum A, NO project slugs)" (read as: Phase C synthesis will produce a kill list limited to infrastructure and components, with no project slugs.)
- `U-1bce0cff` 2026-04-18, commitment, `handoffs/2026-04-18_evolution_burst_closeout.md#L45`: "Phase C Synthesis (next major work, Brock-driven)" (read as: Phase C synthesis using CC1-CC5 outputs is the next major work, driven by Brock: kill list, 75/15/10 roadmap, three-item commit point, AD-022/023/024 drafts.)

### G290: review, commits, origin, push

- `U-2afe7870` 2026-04-18, commitment, `handoffs/2026-04-18_evolution_burst_closeout.md#L42`: "**Push review**: 7 commits ahead of origin. Brock reviews before `git push`." (read as: Brock will review the 7 unpushed commits before pushing to origin.)

### G291: consumer, claudeclaw, jobs, measured

- `U-6f383102` 2026-04-18, decision, `handoffs/2026-04-18_session_close_75_bucket_shipped.md#L76`: "ClaudeClaw + 16 jobs — operator is the consumer; "no measured consumer" was a measurement-gap error" (read as: ClaudeClaw and its 16 jobs were retained because the operator is the consumer; the retirement rationale of no measured consumer was a measurement error.)

### G292: seldon, sfv, paper, database

- `U-0d2a3e89` 2026-04-18, decision, `handoffs/2026-04-18_session_close_75_bucket_shipped.md#L75`: "`seldon-sfv-paper` database — operator decision" (read as: The operator decided to retain the seldon-sfv-paper database during infrastructure retirement.)

### G293: flash, gemini, forward, dual

- `U-ca3d2c62` 2026-04-18, need, `handoffs/2026-04-18_session_close_75_bucket_shipped.md#L27`: "**Note: operator wants gemini-3-flash going forward, not 2.5-flash.**" (read as: The operator wants gemini-3-flash used for dual-model auditing going forward instead of gemini-2.5-flash.)

### G283: section, page, add, api

- `U-a41355f7` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L27`: "Add "Where to Start" section to Ch 10. Half-page, minimum viable provenance starting point." (read as: DG-6: add a 'Where to Start' section to Ch 10 giving a minimum viable provenance starting point.)
- `U-932005b0` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L24`: "Add API vs. fine-tuning TCO section to Ch 14. Half-page to one page." (read as: DG-3: add an API vs. fine-tuning TCO section to Ch 14.)

### G286: phases, clusters, five, book

- `U-e726641e` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L22`: "Five phases: Foundations (Ch 1), Domain Workflows (Ch 2-4), Cross-Cutting Patterns (Ch 5-8), Validity (Ch 9-10), **Delivery** (Ch 11-14). "Phases" not "clusters."" (read as: DG-1: the book is organized into five phases, called 'phases' rather than 'clusters'.)

### G287: clarification, sentence, raters, error

- `U-39548c1c` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L23`: "No error. Cohen's κ (2 raters, classification) and Fleiss' κ (3 raters, harmonization) both correctly applied. One clarification sentence in Ch 8." (read as: DG-2: no error in the kappa usage; add one clarification sentence in Ch 8.)

### G288: evaluation, trap, failure, mode

- `U-910efbda` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L25`: "Add "evaluation trap" as named failure mode in Ch 1. Label all five degradation pathways while in there (resolves CC-9)." (read as: DG-4: name 'evaluation trap' as a failure mode in Ch 1 and label all five degradation pathways.)

### G289: numbers, correct, written, cost

- `U-a1b6fb2b` 2026-04-07, decision, `handoffs/2026-04-07_decision_gates_batch_b.md#L26`: "Numbers are correct as written. Different scopes, already addressed. **Stop re-flagging.**" (read as: DG-5: the cost numbers are correct as written and should not be flagged again.)
