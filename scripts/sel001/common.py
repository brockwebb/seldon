"""SEL-001 shared pieces: configuration, the identifier rules, the task family, and checkpointed runs.

Standard library plus PyYAML only, because two interpreters import it: Seldon's (gold sets, arm O, scoring) and
Squiddy's (arm H, which needs the pinned encoder). Neither arm's code lives here; this is what both must agree on.
The protocol every rule here implements is `evidence/sel001/protocol.md`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SELDON_ROOT = HERE.parent.parent
CONFIG = HERE / "sel001.yaml"

#: The identifiers a task cites (protocol section 3). Order matters for stripping: the compound form first, so
#: `DN-002-R1` is removed whole rather than leaving `-R1` behind. A token ends where its digits end, so `R-112s` and
#: `R-170's` lose their identifier too.
COMPOUND_RE = re.compile(r"\b[A-Z]{2,4}-\d+-R\d+(?![0-9])")
DOC_ID_RE = re.compile(r"\b(?:DN|AD)-\d+(?![0-9])")
RULING_RE = re.compile(r"\bR-\d+(?![0-9])")
STRIP_RES = (COMPOUND_RE, DOC_ID_RE, RULING_RE)

#: A label that names one ruling across a whole graph: Squiddy's `R-nnn`, or a compound `DN-002-R1`. Arnold's
#: `R1` names a ruling only inside its own document.
GLOBAL_LABEL_RE = re.compile(r"^(?:R-\d+|[A-Z]{2,4}-\d+-R\d+)$")

_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[_-]")
_CODE_RE = re.compile(r"^([A-Z]{1,4}-\d+)(?=$|[_.\- ])")
_CORRECTION_SUFFIX_RE = re.compile(r"(?i)[._-]+(?:addendum|erratum)\b.*$")
CORRECTION_NAME_RE = re.compile(r"(?i)addendum|erratum|correction|corrective")


def load_config() -> dict:
    """The harness configuration, with every path expanded. Fails loud on a missing key."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for key in ("evidence_dir", "repos", "graph_dir", "squiddy_python", "k", "k_small", "wilson_z", "set_c",
                "set_b", "diagnostics_b", "run"):
        if key not in cfg:
            raise SystemExit(f"FATAL: {CONFIG} lacks `{key}`")
    for repo in cfg["repos"].values():
        repo["root"] = str(Path(repo["root"]).expanduser())
    cfg["squiddy_python"] = str(Path(cfg["squiddy_python"]).expanduser())
    cfg["evidence_path"] = str(SELDON_ROOT / cfg["evidence_dir"])
    return cfg


def evidence(cfg: dict, name: str) -> Path:
    p = Path(cfg["evidence_path"]) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str))


# ------------------------------------------------------------------------------------------------
# identifiers and stripping
# ------------------------------------------------------------------------------------------------

def strip_identifiers(text: str) -> str:
    """The task text with every compound ruling identifier, `DN-nnn`, `AD-nnn` and `R-nnn` token deleted."""
    for rx in STRIP_RES:
        text = rx.sub("", text)
    return text


def is_global_label(label: str | None) -> bool:
    return bool(label and GLOBAL_LABEL_RE.match(label))


# ------------------------------------------------------------------------------------------------
# a task's family (protocol section 1) and correction files (section 3, set C)
# ------------------------------------------------------------------------------------------------

def stem_nodate(path: str) -> str:
    """`cc_tasks/2026-10-02_KG-004_x.md` -> `KG-004_x`."""
    name = Path(path).name
    if name.endswith(".md"):
        name = name[:-3]
    return _DATE_PREFIX_RE.sub("", name)


def family_key(path: str) -> str:
    """What a task's family shares: its code (`KG-004`) when its name opens with one, else its slug with any
    addendum or erratum suffix removed."""
    stem = _CORRECTION_SUFFIX_RE.sub("", stem_nodate(path))
    m = _CODE_RE.match(stem)
    return m.group(1) if m else stem


def in_family(key: str, path: str) -> bool:
    """Whether the document at `path` belongs to the family `key`: its dateless stem is the key, or opens with the
    key followed by a separator (so `S-001` does not claim `S-0010`)."""
    stem = stem_nodate(path)
    return stem == key or (stem.startswith(key) and stem[len(key):len(key) + 1] in ("_", "-", ".", " "))


# ------------------------------------------------------------------------------------------------
# checkpointed runs (engineering standards section 15)
# ------------------------------------------------------------------------------------------------

def append_row(path: Path, row: dict) -> None:
    """One durable row: written, flushed and fsynced before the next unit starts (15.1)."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_rows(path: Path) -> list[dict]:
    """Every row of a JSONL file, split on LF only. A corrupt line is fatal (standard 4)."""
    if not Path(path).is_file():
        return []
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"FATAL: corrupt row at {path}:{n}: {exc}")
    return out


class Progress:
    """Done/total, rate, ETA and failures, to stdout and a log file, every N units or T seconds (15.3)."""

    def __init__(self, total: int, log: Path, every_units: int, every_seconds: float, name: str):
        self.total, self.log, self.every_units, self.every_seconds, self.name = (
            total, log, every_units, every_seconds, name)
        self.t0 = self.last = time.monotonic()
        self.done = self.new = self.failed = 0

    def say(self, msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {self.name}: {msg}"
        print(line, flush=True)
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def tick(self, *, new: bool, failed: bool = False) -> None:
        self.done += 1
        self.new += int(new)
        self.failed += int(failed)
        now = time.monotonic()
        if new and (self.new % self.every_units == 0 or now - self.last >= self.every_seconds):
            el = now - self.t0
            rate = self.new / el if el else 0.0
            eta = (self.total - self.done) / rate if rate else float("nan")
            self.say(f"{self.done}/{self.total} units ({self.new} this run), {rate:.2f}/s, ETA {eta:.0f}s, "
                     f"failures {self.failed}")
            self.last = now

    def elapsed(self) -> float:
        return time.monotonic() - self.t0


# ------------------------------------------------------------------------------------------------
# statistics
# ------------------------------------------------------------------------------------------------

def wilson(successes: int, n: int, z: float) -> tuple[float, float]:
    """The Wilson score interval for a binomial proportion (Wilson 1927). (0, 0) for n = 0, which is reported as
    such rather than as an interval."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
