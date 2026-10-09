# AD-035 erratum 01: section 2's internal search was overstated, and the library was not consulted

**Date:** 2026-10-09. **Corrects:** `docs/design/AD-035_config_driven_model_selection.md` section 2. The base note is not edited (immutable once committed).

## What was wrong

Section 2 says "Internal precedent (searched: seldon, squiddy, ai-readiness-kg, arnold, icsp_notebook design notes and configs)". That overstates the search.

What was actually done:
- three config files were read;
- a filename glob for a model registry was run;
- the internal precedents listed were recalled from session memory.

No content search of those repositories was run. The Squiddy library graph, the operator's corpus of the literature, was not queried. The note was written from one vendor document plus a lockfile analogy.

This is audit problem 1 (`workbench/2026-10-03_audit_and_decision_probe/cross_project/synthesis/G5_governance.md`, ranked first, REGRESSED), recurring in the session that wrote AD-035.

## What the library holds, queried after the fact (squiddy-library `search`, release m002, 2026-10-09)

- **Chen, Zaharia and Zou 2023, arXiv:2307.09009** (`lesson:2026-04-07_arXiv_2307_09009`, p.1 and p.2). A model served under one name changed behavior substantially between versions three months apart. Results from the "same" LLM cannot be reproduced without knowing which version answered, and continuous monitoring is required. This supports R1 (lock), R6 (served-model receipt) and R7 (change at a boundary).
- **LLM-as-a-Judge survey, arXiv:2411.15594** (`lesson:2026-03-29_arXiv_2411_15594`, p.22 and p.44). The authors call it "evaluation drift": a judge's verdicts move with model updates, so a judge's stability must be tracked across versions. This supports R7's re-pilot of the judge and demand-judge roles on any bump.
- **arXiv:2406.14325** (`lesson:2026-04-13_arXiv_2406_14325`, p.16 and p.21), citing Han et al. 2017, PLoS ONE e0183591. Mandatory checklists increased the reporting of methodological information needed for reproduction by 65% over 943 articles. Voluntary guidelines "may not be enforced consistently". This bears on R5: only a refusing gate holds a rule.

## Effect on the rulings

None reversed. The literature agrees with R1, R5, R6 and R7, but it was found after the rulings, not used to make them.

One gap the literature exposes: AD-035 locks the model and leaves effort implicit (`effort: default`). Under the 5.5 lock, that moved every opus and sonnet role from high to medium effort. Chen et al.'s point applies to any input that changes the instrument, not only its name. This gap is carried into the action-E design rather than patched alone; MODEL-002 was withdrawn for that reason.
