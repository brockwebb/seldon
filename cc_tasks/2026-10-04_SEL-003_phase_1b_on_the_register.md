# SEL-003: AD-031 Phase 1b on the decision register. Three arms (overlap, hybrid, full register) against the frozen bar, on the gold sets SEL-001 drew

**Repo:** seldon (reads squiddy and arnold by path). Branch `feat/SEL-003` from main. L4: commit, merge, push.
**Governing:** AD-033 section 6 (the pre-registration, committed in `419c30e` before anything was measured). It is
frozen: nothing in it is tuned. Read AD-033 in full, AD-031, `docs/SEL-001_delivery_report.md` and SEL-001's scripts
and evidence (its gold-set construction, seed and stripping), `docs/SEL-002_delivery_report.md`, and Squiddy DN-042
plus `squiddy/spend.py`. Glob and read sibling `*SEL-003*ADDENDUM*.md`.
**Model spend:** arm F only, under the DN-042 governor: one call per task per replicate, two replicates, about 107
tasks. Notional before the pilot: about 11M weighted tokens (the register is about 660 active records, larger than
AD-033's 450). A 5-task pilot measures the estimate first. A `band_stop` waits for the operator's dated
`spend_approval.yaml`; do not work around it. Arms O and H: zero model calls.
**Network:** the model CLI for arm F; git push.

## Declarations, made before any measurement (not tuning)

1. **Arm F's rendering.** Each record is given to the arm F call as id plus `statement`, with the verbatim source in
   place of the statement where `statement_check` is `failed`. Reason: id, statement and full verbatim for every
   record exceeds what one call should carry. Arms O and H index id, statement and verbatim source, as section 6
   says. Before anything runs, count tokens for both renderings per task scope and report them.
2. **Scope per task.** The task's own repository register plus its imports (Arnold's tasks see arnold and squiddy).
   Active accepted records only.
3. **Arm F model and effort.** Use the kit's default validator model at default effort, recorded in the evidence.
   SEL-002 G6 (`--effort low`) was measured on yes/no verdicts, not on ranking; it is not carried over here.

## Steps

1. **Gold sets.** Rebuild A, B and C exactly as SEL-001 did (same tasks, same seed, same stripping), then re-resolve
   the gold identifiers through the register. Write both versions (SEL-001's 733 pairs and the re-resolved set) to
   `evidence/sel003/gold/` with sha256 values, committed before any arm runs. The bar is judged on the re-resolved
   set.
2. **Positive controls.** For each B task, write one planted record that contradicts that task's text in its own
   words, by script, from the task text. Plant it into a copy of the scoped register used only by this measurement.
   The real registers are never written. Record each plant and its target task.
3. **Arm O.** Seldon's concept-overlap score over record text, unchanged code.
4. **Arm H.** Squiddy's hybrid `search` over an index whose rows are records only, with SEL-001's frozen `index:`
   block.
5. **Arm F.**
   - A 5-task pilot under a declared job sets the estimate.
   - Then the full run: two replicates, record order shuffled per call (seed 20261004 plus replicate and task
     index).
   - Each call returns at most 10 record ids, ranked, that constrain or conflict with the task.
   - Report agreement between the replicates (Cohen's kappa and Gwet's AC1 on per-record inclusion) and score each
     replicate separately.
6. **Measures** (section 6): recall@5, recall@10 and MRR on A; Wilson intervals plus a cluster bootstrap over tasks
   (10,000 resamples, seed 20261004); B hits at k = 10; C candidate counts; the split by gold form. Report each arm's
   plant retrieval at k = 10. An arm whose plant is missed is reported as not working, and its verdict is not cited.
7. **Outcome rule** as written in section 6.
   - If an arm meets the bar (recall@10 at or above 0.80 on A, and 5 of 5 B), report it.
   - If more than one meets it, name the cheaper by measured tokens per task.
   - If none meets it, name every miss by record.
   - This task measures only. Switching registration's binding to the winning arm is a later task.
8. **Record.**
   - Register each arm's recall@10, B hits and tokens per task as Seldon Results.
   - Write `docs/SEL-003_delivery_report.md`. Lead with the verdict per arm against the bar, then the misses by
     record, then cost: estimate, actual and ratio.
   - Suite green, `seldon verify`, commit, merge, push, `seldon cc complete`.
   - End by printing this session's token usage.
