"""Judge calibration (AD-037-R5, R3): three separate numbers, each with its interval and its n.

The lesson this module consumes (AD-032 FC-26), recorded in the decision register: squiddy DN-022 §1, 2026-09-29:
ABBA and replicate kappa reported as judge calibration; neither measures self-preference.

- **Position bias** is the ABBA flip rate: the share of (item, half, replicate) readings whose verdict changes when
  the order is reversed. The order is item order within a review batch for a single-item checker and pair order for
  a pairwise judge; the computation is the same, so a row carries only `order` (`AB` or `BA`). Wilson-95 interval
  (Wilson 1927).
- **Test-retest reliability** is replicate Cohen's kappa (Cohen 1960) over (item, half, order) readings made twice.
  A Wilson interval is for a binomial proportion and does not fit kappa, so kappa carries Cohen's (1960)
  large-sample interval, kappa +- z * sqrt(p_o (1 - p_o) / (n (1 - p_e)^2)), clamped to [-1, 1]; the raw agreement
  p_o, a proportion, carries its Wilson-95 interval.
- **Self-preference** is the catch-rate difference between reference-text plants and generator-style plants
  (AD-037-R3), each catch rate over one canonical reading per item (replicate 1, order AB) with its Wilson-95
  interval; the difference (reference minus generator: positive means the judge misses more defects in text in the
  generator's style) carries Newcombe's (1998) hybrid score interval, method 10, built from the two Wilson intervals.

A report missing any of the three is refused (`calibration_incomplete`). A report passes when it is complete and its
generator-style catch rate's Wilson-95 lower bound meets the bar with at least the bar's n (AD-037-R3; values in
`models/registry.yaml` `calibration.bar`).
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import yaml

COMPONENTS = ("position_bias", "test_retest", "self_preference")
HALVES = ("generator", "reference")
ORDERS = ("AB", "BA")
CANONICAL = (1, "AB")          # the reading each item's catch is counted on: replicate 1, order AB


class CalibrationIncomplete(Exception):
    """`calibration_incomplete`: a report without all three numbers (AD-037-R5)."""


class CalibrationSetError(Exception):
    """The calibration set or the verdicts are not in the declared format."""


# ------------------------------------------------------------------------------------------- intervals

def wilson(k: int, n: int, z: float) -> list[float]:
    """Wilson (1927) score interval for k successes in n trials."""
    if n <= 0:
        raise ValueError("a Wilson interval needs n > 0")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def newcombe_difference(k1: int, n1: int, k2: int, n2: int, z: float) -> dict:
    """p1 - p2 with Newcombe's (1998) hybrid score interval (method 10)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return {"estimate": d, "ci95": [lo, hi], "method": "Newcombe 1998 hybrid score (method 10)"}


def cohen_kappa(pairs: list[tuple[str, str]], z: float) -> dict:
    """Cohen's (1960) kappa over paired readings, its large-sample SE and interval, and the raw agreement."""
    n = len(pairs)
    if n == 0:
        raise ValueError("kappa needs at least one pair")
    agree = sum(a == b for a, b in pairs)
    po = agree / n
    first, second = Counter(a for a, _b in pairs), Counter(b for _a, b in pairs)
    pe = sum((first[c] / n) * (second[c] / n) for c in set(first) | set(second))
    if pe >= 1.0:
        kappa, se = 1.0, 0.0           # one category on both readings: agreement is total and chance-level alike
    else:
        kappa = (po - pe) / (1 - pe)
        se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    return {"kappa": kappa, "kappa_se": se,
            "kappa_ci95": [max(-1.0, kappa - z * se), min(1.0, kappa + z * se)],
            "kappa_method": "Cohen 1960 large-sample interval", "n": n,
            "agreement": {"estimate": po, "ci95": wilson(agree, n, z), "n": n, "k": agree}}


# --------------------------------------------------------------------------------------- set and verdicts

ITEM_KEYS = ("id", "defect_class", "receipt", "criterion", "reference", "generator")


def load_set(path: Path | str) -> dict:
    """The calibration set, validated: `{item id: item}`."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise CalibrationSetError(f"{path}: no `items:` list")
    out = {}
    for it in items:
        missing = [k for k in ITEM_KEYS if k not in it]
        if missing:
            raise CalibrationSetError(f"{path}: item {it.get('id')!r} lacks {missing}")
        ref = it["reference"]
        if not all(k in ref for k in ("source", "original", "planted", "plant")):
            raise CalibrationSetError(f"{path}: item {it['id']!r} reference needs source, original, planted, plant")
        if it["id"] in out:
            raise CalibrationSetError(f"{path}: item id {it['id']!r} appears twice")
        out[it["id"]] = it
    return out


def load_verdicts(path: Path | str) -> list[dict]:
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        raise CalibrationSetError(f"{path}: no verdict rows")
    return rows


def _check_rows(items: dict, rows: list[dict]) -> None:
    for r in rows:
        if r.get("item") not in items:
            raise CalibrationSetError(f"verdict row names item {r.get('item')!r}, which the set does not hold")
        if r.get("half") not in HALVES or r.get("order") not in ORDERS or not isinstance(r.get("replicate"), int):
            raise CalibrationSetError(f"verdict row {r} needs half in {HALVES}, order in {ORDERS}, an int replicate")
        if not isinstance(r.get("verdict"), str):
            raise CalibrationSetError(f"verdict row {r} has no string `verdict`")


# ---------------------------------------------------------------------------------------- the report

def calibrate(items: dict, rows: list[dict], cfg: dict) -> dict:
    """The three numbers from one judge's verdicts on the set. Raises `CalibrationIncomplete` when the verdicts
    cannot give one of them (no reversed-order pair, no replicate pair, or a half with no canonical reading)."""
    _check_rows(items, rows)
    z, label = float(cfg["z"]), cfg["defect_label"]
    by = {(r["item"], r["half"], r["replicate"], r["order"]): r["verdict"] for r in rows}
    missing = []

    flips, npairs = 0, 0
    for (i, h, rep, o), v in by.items():
        if o == "AB" and (i, h, rep, "BA") in by:
            npairs += 1
            flips += v != by[(i, h, rep, "BA")]
    position = ({"estimate": flips / npairs, "ci95": wilson(flips, npairs, z), "n": npairs, "k": flips,
                 "method": "ABBA flip rate, Wilson 1927"} if npairs else None)
    if position is None:
        missing.append("position_bias")

    pairs = [(v, by[(i, h, 2, o)]) for (i, h, rep, o), v in by.items() if rep == 1 and (i, h, 2, o) in by]
    retest = cohen_kappa(pairs, z) if pairs else None
    if retest is None:
        missing.append("test_retest")

    halves = {}
    for h in HALVES:
        canon = [v for (i, hh, rep, o), v in by.items() if hh == h and (rep, o) == CANONICAL]
        if canon:
            k = sum(v == label for v in canon)
            halves[h] = {"estimate": k / len(canon), "ci95": wilson(k, len(canon), z), "n": len(canon), "k": k}
    self_pref = None
    if len(halves) == 2:
        g, rf = halves["generator"], halves["reference"]
        self_pref = {**halves, "difference": newcombe_difference(rf["k"], rf["n"], g["k"], g["n"], z),
                     "sign": "reference minus generator; positive means the judge misses more generator-style plants"}
    else:
        missing.append("self_preference")
    if missing:
        raise CalibrationIncomplete(f"calibration_incomplete: the verdicts give no {', '.join(missing)} "
                                    f"(AD-037-R5: all three numbers, or no report)")
    rep = {"schema": 1, "position_bias": position, "test_retest": retest, "self_preference": self_pref}
    rep["passes"] = passes(rep, cfg)
    rep["bar"] = dict(cfg["bar"])
    return rep


def require_complete(report: dict) -> None:
    """Refuse a report missing any of the three numbers (AD-037-R5)."""
    missing = [c for c in COMPONENTS if not isinstance(report.get(c), dict)]
    sp = report.get("self_preference") or {}
    if not missing and not all(isinstance(sp.get(h), dict) for h in HALVES + ("difference",)):
        missing.append("self_preference")
    if missing:
        raise CalibrationIncomplete(f"calibration_incomplete: the report has no {', '.join(missing)} (AD-037-R5)")


def passes(report: dict, cfg: dict) -> bool:
    """Complete, and the generator-style catch rate's Wilson-95 lower bound meets the bar with at least its n."""
    require_complete(report)
    g = report["self_preference"]["generator"]
    bar = cfg["bar"]
    return int(g["n"]) >= int(bar["n_min"]) and float(g["ci95"][0]) >= float(bar["generator_catch_lower"])


def report_path(home: Path, judge_model: str, generator_model: str) -> Path:
    """A report is keyed by the judge's and the generator's lock ids, so a lock bump of either voids it
    (AD-035-R7). `home` is the models home; the directory is `calibration.report_dir` in its registry."""
    reg = yaml.safe_load((Path(home) / "registry.yaml").read_text(encoding="utf-8")) or {}
    rdir = (reg.get("calibration") or {}).get("report_dir")
    if not rdir:
        raise CalibrationSetError(f"{Path(home) / 'registry.yaml'}: no `calibration.report_dir`")
    return Path(home) / rdir / f"{judge_model}__over__{generator_model}.json"


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------- parallel dispatch held

#: AD-037-R9: the ruling that holds `dispatch.max_parallel` at 1; an opt-in record is anchored at it.
PARALLEL_RULING = "seldon:AD-037-R9"
#: `dispatch.max_parallel` when a block names none (AD-034's default).
MAX_PARALLEL_DEFAULT = 1


def parallel_opt_ins(records) -> set[str]:
    """Repositories opted into parallel dispatch: the scope of every accepted record, other than AD-037-R9 itself,
    whose `rationale.anchor` is `AD-037-R9` (the measured-demand opt-in R9 allows once its stations are live)."""
    out: set[str] = set()
    for r in records:
        if r.status != "accepted" or r.id == PARALLEL_RULING:
            continue
        if ((r.get("rationale") or {}).get("anchor") or "") == PARALLEL_RULING.split(":", 1)[1]:
            out |= set(r.get("scope") or [])
    return out


#: This repository: AD-037 and its register live here, so the dispatcher of any project reads its opt-ins from here too.
SELDON_ROOT = Path(__file__).resolve().parents[2]


def parallel_opted_in(project_dir: Path, config: dict) -> bool:
    """AD-037-R9 AT THE DISPATCHER (QC-001 premise 7: the hold was a test, not a refusal). True when an accepted record
    anchored at AD-037-R9 names this project in its scope. Records are read from this project's register and its
    imports, and from seldon's register, where AD-037 lives; a project with no register of its own reads seldon's."""
    from seldon.core import decisions
    repo = Path(project_dir).resolve().name
    seldon_cfg = yaml.safe_load((SELDON_ROOT / "seldon.yaml").read_text(encoding="utf-8")) or {}
    recs = []
    for root, cfg in ((Path(project_dir), config or {}), (SELDON_ROOT, seldon_cfg)):
        if decisions.settings(root, cfg) is None:
            continue
        u = decisions.universe(root, cfg)
        recs += [r for rp in u.scope_repos() for r in u.records(rp).values()]
    return repo in parallel_opt_ins(recs)


def parallel_findings(seldon_yaml: Path, opted_in: set[str]) -> list[str]:
    """A `dispatch:` block whose `max_parallel` is above 1 for a repository with no opt-in record (AD-037-R9)."""
    cfg = yaml.safe_load(Path(seldon_yaml).read_text(encoding="utf-8")) or {}
    block = cfg.get("dispatch")
    if not isinstance(block, dict):
        return []
    n = block.get("max_parallel", MAX_PARALLEL_DEFAULT)
    repo = Path(seldon_yaml).resolve().parent.name
    if isinstance(n, int) and not isinstance(n, bool) and n <= 1:
        return []
    if repo in opted_in:
        return []
    return [f"{seldon_yaml}: dispatch.max_parallel is {n!r} with no accepted record anchored at AD-037-R9 naming "
            f"{repo!r} in its scope (AD-037-R9: parallel dispatch stays at 1)"]
