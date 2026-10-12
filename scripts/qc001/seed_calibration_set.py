"""QC-001 Part C.3: seed the judge-calibration set (AD-037-R3) from this week's real defects. Zero model calls.

Each item is one real defect, cited by its receipt, turned into a planted defect of the same class. Its reference half
is a passage from a library-held document published before 2022, human-authored: the document's abstract as the
squiddy library manifest holds it (`graphs/library/corpus/manifest.yaml`), verbatim, with one minimal edit that plants
the defect. Never Claude-written text. The generator-style half is a slot with its instructions: the generator model
writes it in QC-002, which spends; nothing here calls a model.

A plant must not depend on outside knowledge to be caught: the passage itself shows the defect (a count that
disagrees with what it counts, a parameter left at an unstated default, a label in a second form, one label on two
items, a loop with no bound), so a catch measures the judge's reading, not its recall of the paper.

    python scripts/qc001/seed_calibration_set.py      # writes models/calibration/set.yaml
"""
from __future__ import annotations

from pathlib import Path

import yaml

SELDON = Path(__file__).resolve().parents[2]
LIBRARY = Path("/Users/brock/GitHub/squiddy/graphs/library/corpus/manifest.yaml")
OUT = SELDON / "models" / "calibration" / "set.yaml"

CRITERIA = {
    "premise_found_wrong": "Every count, date, version or state the passage asserts agrees with what the passage "
                           "itself lists or reports elsewhere.",
    "implicit_default": "Every setting a reported result depends on is stated with its value, not left to an "
                        "unstated default.",
    "unparsed_label": "Every reference label in the passage uses the one label form the passage uses for the rest.",
    "label_collision": "Every numbered label in the passage names exactly one item.",
    "unbounded_resource": "Every iterative or repeated procedure the passage describes states its bound.",
}

GENERATOR_INSTRUCTIONS = (
    "QC-002: the generator role being calibrated writes a passage of similar length on the same topic, in its own "
    "style, without seeing the reference passage's wording; then the same defect class is planted in it by one "
    "minimal edit under the same criterion. Record the passage, the plant and the call's receipt here, and set "
    "`status: written`.")

#: (item id, defect class, receipt of the real defect, one line on it, library id, plant from, plant to)
SEEDS = [
    ("premise-model001-inventory", "premise_found_wrong",
     "seldon:cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md:38",
     "MODEL-001's inventory counted 13 ai-readiness-kg launchers where there was 1 exec site.",
     "lesson:2024-05-17_arXiv_1701_00160", "The tutorial describes:", "The tutorial describes six topics:"),
    ("premise-model001-import", "premise_found_wrong",
     "seldon:cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md:41",
     "MODEL-001 assumed arnold's and squiddy's environments could import seldon; they could not.",
     "lesson:2026-02-22_arXiv_2112_09332", "Our best model is obtained by fine-tuning GPT-3",
     "Our best model is obtained by fine-tuning GPT-2"),
    ("premise-pa001-hook", "premise_found_wrong",
     "seldon:cc_tasks/2026-10-09_PA-001_prior_art_receipts_gate_RESULT.md:36",
     "PA-001 assumed a git pre-commit hook existed; `core.hooksPath` named a removed path.",
     "lesson:2024-12-04_10_1177_1461444814538646", "the Netflix Prize (2006–2009), a contest",
     "the Netflix Prize (2006–2009), a five-year contest"),
    ("premise-pa001-pin", "premise_found_wrong",
     "seldon:cc_tasks/2026-10-09_PA-001_prior_art_receipts_gate_RESULT.md:42",
     "PA-001 found the governed pin stale, so 19 governed documents were uncataloged against the assumed state.",
     "lesson:2026-02-21_arXiv_1904_10509", "We also introduce a)", "We also introduce four changes: a)"),
    ("premise-sq010-binding", "premise_found_wrong",
     "squiddy:cc_tasks/2026-10-10_SQ-010_governed_admission_dn043_RESULT.md:44",
     "DN-043 R-186 assumed registration binds by retrieval from the governed graph; it binds register records.",
     "lesson:2026-02-22_arXiv_1809_07124", "To date, we have already hosted one competition, and our next one",
     "To date, we have hosted no competition, and our next one"),
    ("premise-sq010-cause", "premise_found_wrong",
     "squiddy:cc_tasks/2026-10-10_SQ-010_governed_admission_dn043_RESULT.md:45",
     "SQ-010's stop condition named stage 04 snapshot as the cause; the file is stage 06 read's output.",
     "lesson:2026-04-12_arXiv_2112_01488", "while reducing the space footprint of late interaction models by 6--10$\\times$",
     "while increasing the space footprint of late interaction models by 6--10$\\times$"),
    ("default-model002-effort", "implicit_default",
     "seldon:cc_tasks/2026-10-09_MODEL-002_explicit_effort_hermetic_model_tests.md:16",
     "20 of 22 registry roles ran at `effort: default`, which moved from high to medium with the 5.5 lock.",
     "lesson:2026-01-12_arXiv_1807_04667", "while using the PPG heart rate sensor infrequently (e.g., 20.25% of the samples)",
     "while sampling the PPG heart rate sensor at its default rate"),
    ("label-ad035-unparsed", "unparsed_label",
     "seldon:docs/design/AD-036_prior_art_receipts_gate.md:143",
     "AD-035's rulings were written as `## AD-035-Rn.` headings, a form no configured label pattern read.",
     "lesson:2026-03-14_10_1515_forma_2016_0023", "follows K. Knopp [8], [1] and [6]",
     "follows K. Knopp [8], (1) and [6]"),
    ("label-dn043-r181", "label_collision",
     "squiddy:docs/design/2026-10-10_DN-043_ADDENDUM_01_r181_renumbered_r188.md:7",
     "DN-043 labelled its first ruling R-181, which DN-042 already held.",
     "lesson:2026-02-08_arXiv_1701_05517", "4) We introduce additional short-cut connections",
     "3) We introduce additional short-cut connections"),
    ("bound-sq010-disk", "unbounded_resource",
     "squiddy:docs/evidence/sq010/disk_incident.md:25",
     "SQ-010 ran with no disk ceiling or checkpoint and filled the volume's last 4.4 GB.",
     "lesson:2026-02-22_arXiv_2110_14168", "At test time, we generate many candidate solutions and select the one",
     "At test time, we generate candidate solutions until the verifier accepts one, and select the one"),
]


def main() -> int:
    lib = yaml.safe_load(LIBRARY.read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in (lib.get("documents") or [])}
    items = []
    for item_id, cls, receipt, defect, lib_id, frm, to in SEEDS:
        d = docs[lib_id]
        original = " ".join(str(d["abstract"]).split())
        if str(d.get("publication_date")) >= "2022":
            raise SystemExit(f"FATAL: {lib_id} is dated {d.get('publication_date')}; reference text is pre-2022")
        if original.count(frm) != 1:
            raise SystemExit(f"FATAL: {item_id}: the plant's text occurs {original.count(frm)} times in {lib_id}")
        items.append({
            "id": item_id, "defect_class": cls, "receipt": receipt, "defect": defect, "criterion": CRITERIA[cls],
            "reference": {"source": {"library_id": lib_id, "title": d.get("title_authority") or d.get("title"),
                                     "publication_date": str(d.get("publication_date")), "locator": "abstract",
                                     "manifest": str(LIBRARY), "abstract_whitespace": "collapsed to single spaces"},
                          "original": original, "planted": original.replace(frm, to, 1),
                          "plant": {"from": frm, "to": to}},
            "generator": {"status": "slot", "instructions": GENERATOR_INSTRUCTIONS}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = ("# The judge-calibration set (AD-037-R3), seeded by QC-001 Part C.3 from scripts/qc001/seed_calibration_set.py.\n"
              "# Do not edit by hand: change the script and re-run it. Generator halves are slots QC-002 fills.\n")
    OUT.write_text(header + yaml.safe_dump({"schema": 1, "criteria": CRITERIA, "items": items}, sort_keys=False,
                                           allow_unicode=True, width=120), encoding="utf-8")
    by = {}
    for it in items:
        by[it["defect_class"]] = by.get(it["defect_class"], 0) + 1
    print(f"{len(items)} items -> {OUT}: {by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
