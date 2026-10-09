# AD-035 ADDENDUM 01: its prior-art section, verified (AD-036-R7)

**Date:** 2026-10-09. **Task:** PA-001 (`459f463e`). **Amends:** nothing in AD-035's rulings. AD-035
is immutable; this addendum records what `seldon prior-art verify` found and carries, as receipts,
the searches its section 2 should have run. AD-035 is in the AD-036 baseline (it was on main at
PA-001's merge), so the gate does not require it to pass; R7 requires it to be checked and the
result written down.

## 1. AD-035 verified as written

`seldon prior-art verify docs/design/AD-035_config_driven_model_selection.md`, 2026-10-09, AD-035
sha256 `868a0373a135`, governed-ledger event `9d47856e`: **FAIL**.

- `missing: no ### External subsection`, `missing: no ### Internal subsection`. Section 2 uses bold
  run-in labels (`**External**`, `**Internal precedent**`), not subsections.
- Had they been subsections, both would be empty of receipts: every entry is a recalled citation.
  AD-035 erratum 01 already records that the "searched" claim was a filename glob and session
  memory, and that the library was not consulted. The gate reproduces that finding mechanically.

## 2. What the searches return

The library rows AD-035 erratum 01 cites, re-run with the queries AD-036 section 2 used, and the
internal rulings AD-035 restated without finding (AD-036 section 1). With these receipts, AD-035 plus
this addendum is re-verified; the RESULT names the event.

## 3. Prior art

### External

- library receipt: query "checklist compliance enforced gate pre-registration systematic review protocol reduces errors" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-04-13_arXiv_2406_14325#p21:138:1384-1675, lesson:2026-04-13_arXiv_2406_14325#p16:104:1865-2521, lesson:2026-02-22_arXiv_2502_12110#p22:436:25-451
- library receipt: query "LLM behavior drift over time model version changes reproducibility of results" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-03-29_arXiv_2411_15594#p44:613:2025-3138, lesson:2026-03-29_arXiv_2411_15594#p22:329:2228-3056, lesson:2026-04-07_arXiv_2307_09009#p2:40:494-2812, lesson:2026-04-07_arXiv_2307_09009#p1:8:1723-2355
- web receipt: url https://code.claude.com/docs/en/model-config | retrieved 2026-10-09

### Internal
ai-readiness-kg methodology section 1: model identity is a gate; a model change is a new instrument (AD-035 R6, R7):
- internal receipt: query "model identity gate" | repo ai-readiness-kg@7e62f24e23b7ea8a61f9c68de906be3db6b8a162 | hits docs/research/kg_construction_methodology.md:8

section 7 rule 5: verify product facts in platform docs before pinning a model (the MODEL-001 defect, paid for in August):
- internal receipt: query "product facts pinning" | repo ai-readiness-kg@7e62f24e23b7ea8a61f9c68de906be3db6b8a162 | hits docs/research/kg_construction_methodology.md:68

squiddy R-30: a new CLI version is a config edit and a new pilot (cited by AD-035 from memory):
- internal receipt: query "new version pilot" | repo squiddy@1cc6fc2d4e7b289737c1bccc210a6166707480ad | hits docs/decisions/register/00030_squiddy-r-30_accept.yaml:13, docs/decisions/register/00030_squiddy-r-30_accept.yaml:30

squiddy DN-042: the one machine-wide ledger AD-035 R1 took as its pattern:
- internal receipt: query "machine-wide spend ledger" | repo squiddy@1cc6fc2d4e7b289737c1bccc210a6166707480ad | hits docs/design/2026-10-04_DN-042_spend_governor_reserve_bands_measured_estimates.md:1, docs/design/2026-10-04_DN-042_spend_governor_reserve_bands_measured_estimates.md:20
