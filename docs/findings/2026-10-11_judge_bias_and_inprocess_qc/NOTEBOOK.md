# Judge bias and in-process quality control: evidence from the 2026-10-11 ai-readiness Desktop thread

Written 2026-10-11 by the ai-readiness-kg Desktop session (Claude Fable 5.1), at the operator's request, so the evidence is not left in chat. Nothing here is a decision. Home when filed: see the bottom section.

## 1. Question

The operator asked for an in-process quality evaluator for long-running dispatched sessions (a "garbage guard"), and set a rule for judges: the next higher tier model checks the work; where there is no higher tier, use adversarial or different personas; no paid ensemble. He asked that the science be consulted, not memory.

## 2. Sources (fetched 2026-10-11 by web search; each was read at the abstract or the conclusion, not in full)

| # | Citation | Locator | What it supports |
|---|---|---|---|
| S1 | Pombal, Rei, Martins (2026). Self-Preference Bias in Rubric-Based Evaluation of Large Language Models. | arXiv:2604.06996 (v3, 3 Aug 2026) | Self-preference persists on objective, programmatically verifiable rubrics: on rubrics the generator failed, judges were more than 50% more likely to mark them satisfied when the output was their own. The bias extends to the judge's own model family. |
| S2 | Mahbub, Feng (2026). Mitigating Self-Preference by Authorship Obfuscation. AAAI 40(44): 37701-37708. | doi:10.1609/aaai.v40i44.41105 | Light perturbation (synonym replacement) reduces self-preference; fuller style neutralization lets it recover. Obfuscation is a partial fix. |
| S3 | UDA: Unsupervised Debiasing Alignment for Pair-wise LLM-as-a-Judge. | arXiv:2508.09724 | Self-preference is heterogeneous: on Arena Hard it ranges from -38% to +90% across judges. Some models under-rate their own output. |
| S4 | Ji (2026). More Debate, Same Evidence: Structural Limits of Homogeneous Multi-Agent Groundedness. | arXiv:2608.00243 | A homogeneous three-agent panel moved accuracy from +8.5 to -4.4 points against a single agent across six benchmarks; correlated persona errors; discussion recalibrates existing judgments. |
| S5 | Stop Overvaluing Multi-Agent Debate: We Must Rethink Evaluation and Embrace Model Heterogeneity (2025). | arXiv:2502.08788 | Multi-agent debate often fails to beat single-agent baselines; model heterogeneity consistently improves it. |
| S6 | Beyond Symmetric Agents: Cognitive Diversity and Multi-Agent Debate in Small Language Models (2026). | arXiv:2609.35875 | Heterogeneous teams lose to majority votes over their own rosters; accuracy rises with member capability, not diversity. Supports "a stronger checker" on capability. |
| S7 | DynSTEER: Dynamic Stage-wise Trajectory Evaluation and Execution-time Review for Agents (2026). | arXiv:2609.14637 | Stage-wise evaluation at key execution nodes, early termination of unrecoverable runs; reports 17.74% of execution steps saved. |
| S8 | Zhuge et al. Agent-as-a-Judge: Evaluate Agents with Agents. ICML 2025 (PMLR 267). | arXiv:2410.10934 | An agent judge with tools that inspects intermediate steps aligned with human consensus about 90% of the time against about 70% for an LLM judge (DevAI benchmark). |
| S9 | Panickssery, Bowman, Feng (2024). LLM evaluators recognize and favor their own generations. | cited by S1, S3 and others; not fetched directly | Origin of the self-recognition and self-preference link. Replicated by S1 in 2026. |

Not verified, from Desktop memory only, must be fetched before any citation: Fagan (1976) on design and code inspection; Deming on ceasing dependence on mass inspection.

## 3. Internal record consulted

- squiddy `docs/design/2026-09-29_kill_stands_postmortem_before_any_lift.md` (DN-022) section 1: judge calibrated with ABBA 26 of 26 and replicate kappa 0.874 (scores) and 0.822 (preferences). **Correction recorded here:** ABBA counterbalancing measures position (order) bias and replicate kappa measures test-retest reliability. Neither measures self-preference. DN-022 itself notes the declared self-preference risk would have favoured arm T and T lost, so the bias did not flip that verdict; its size on this portfolio's work is unmeasured.
- seldon `docs/design/AD-032_factory_control_design.md`: FC-10 (SPC on rated stages), FC-27 (positive controls), FC-28 (andon), FC-29 (huddle) are the controls this work would build. All proposed, none built for Claude Code sessions.
- Prior-art receipts run 2026-10-11 from ai-readiness-kg (the three ai-readiness-kg receipts were written into that repo by mistake and now sit in this folder as `prior_art_queries_written_into_ai-readiness-kg.jsonl`, see 4a): "stop the line andon" (hits in AD-032 and squiddy DN-042); "quality evaluator in-process" (internal none); "ABBA judge order" (squiddy DN-022, wintermute tevv A2). The library arm returned only lexical noise: none of S1 to S8 is in the library graph.

## 4. Positions proposed by Desktop (for the Seldon AD to decide, not decided here)

1. Check by execution wherever a criterion is checkable; no judge reads what can be run (S1 is about judges reading objective criteria).
2. A reading judge is at least one tier above the generator, in a fresh context (operator's rule; S6 on capability). It is not independent of family bias (S1).
3. Family self-preference is measured on this portfolio's own work with planted defects written in the generator's style; a catch rate below a pre-registered bar triggers a cross-family check. Until then, no ensemble (operator's position, now with an instrument behind it).
4. No same-model persona panels as a substitute for model diversity (S4, S5).
5. In-process control for dispatched sessions: pre-dispatch premise review, first-article inspection, milestone sampling with earned value, andon plus huddle (S7, S8, AD-032).

## 4a. Defect found 2026-10-11 22:36: a Desktop prior-art search stalled the ai-readiness-kg queue for 9 hours

The five prior-art searches in section 3 were run from Desktop with `project_dir` ai-readiness-kg. Seldon's `prior-art/1` tool resolves the receipt log through `seldon.yaml` `prior_art: ref:` and wrote it into that repository as an untracked `state/prior_art_queries.jsonl`, with no commit path. The dispatcher's c7 check then found a dirty tree and held task 93333bc9 from 2026-10-11T17:37:47Z (`dispatch_stuck` at 17:47:51Z, 108 passes by 22:36 local). The notification fired and nothing acted on it. The 2026-10-09 c7 fix worked as designed: the event named the path. Desktop moved the five receipt lines here (`prior_art_queries_written_into_ai-readiness-kg.jsonl`) to clear the tree.

For the Seldon AD: (a) a tool that writes into a project's tree owns its commit, or writes outside the tree; this is the same class as the registration-without-commit defect (`1267b87d`); (b) a `dispatch_stuck` notification with no response for N hours is exactly an andon case (FC-28) with no one answering the cord: the AD should say what answers it when the operator is away.

## 5. Home when filed

- **S1 to S9 (the literature):** admitted to the Squiddy library graph through its one-document maintenance path, so the prior-art library arm finds them next time. Squiddy/Seldon Desktop thread, Squiddy task.
- **Positions 1 to 5:** the next Seldon AD (in-process quality control for dispatched sessions), with its rulings recorded through `seldon decision` so registration binds them. Seldon repo, written from the Squiddy/Seldon Desktop thread.
- **The DN-022 correction (section 3):** a lesson under AD-032 FC-26, closed as a mechanism (a judge-calibration check that reports self-preference separately from position bias), not as prose.
- **This notebook:** filed with the AD and hashed, like the 2026-10-03 folder.
