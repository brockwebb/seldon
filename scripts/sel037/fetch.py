"""SEL-037 Part B: fetch the open texts SEL-036 could not reach, reading robots.txt first.

    <squiddy venv>/bin/python scripts/sel037/fetch.py            # run, or resume: the same command
    <squiddy venv>/bin/python scripts/sel037/fetch.py --plan     # the units, no request

Run from the seldon checkout's root with squiddy's interpreter: the robots reading is squiddy's own
(`squiddy.posture.Observer`, RFC 9309 clause by clause, DN-055 R-241), imported and not copied, and so is the PDF text
check (`squiddy.acquire.text_chars`, the reader squiddy's acquire uses on a held file). The HTTP client, the allowlist
on every redirect hop, the snapshot writer (raw bytes plus the form-feed `.txt` derivative) and the posture vocabulary
are SEL-036's (`scripts/sel036/resolve.py`), imported. What this adds is the step SEL-036's fetcher skipped: robots.txt
is read for every origin before any document there is asked for (and before a discovery page is), and a URL it
disallows is a recorded `robots_disallowed` posture, never fetched.

Every target is in scripts/sel037/sel037.yaml. The catalog takes the results through scripts/sel036/build_candidates.py,
which applies this checkpoint as an overlay (`acquired_overlays` in scripts/sel036/sel036.yaml).

**Checkpointing (~/GitHub/CLAUDE.md section 15; SEL-036's resolver's pattern):**

- **Unit of work:** one target (its robots reads, its discovery page, its fetches).
- **Key:** sha256 of (FETCH_VERSION, the target's whole spec). A changed target is a new key.
- **Checkpoint:** one JSON line per finished unit, flushed and fsynced before the next unit starts; re-running is the
  resume. A unit whose row carries `error` (a crash inside it) is asked again once per run.
- **Progress:** every `progress_seconds` and at the end, to stdout and `log`.
- **Pilot:** the first `pilot_units` units of a fresh checkpoint are timed and a projection printed before the rest.
- **Ceilings:** `ceiling_requests` and `ceiling_wall_seconds` stop new units; exit 3 naming the ceiling.
- **Failures are rows:** a refusal is an outcome (`manual`, with status, first bytes and time); an exception is a row
  with `error`.

`--fake-sleep-s S` replaces the network with SEL-036's deterministic stand-in (every request logged to calls.txt);
tests/test_sel037_fetch_checkpoint.py SIGKILLs a run mid-loop and resumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import types
import urllib.parse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "sel036"))
import resolve as R  # noqa: E402  (SEL-036's client, snapshot writer, checkpoint helpers and posture vocabulary)

#: Bumped when what a unit does changes: every key changes with it.
FETCH_VERSION = "sel037-fetch/2"   # 2: robots hops off the Network line named; every discovered link tried
NEED = ("checkpoint", "log", "archive_raw_dir", "archive_text_dir", "user_agent", "timeout_seconds", "max_redirects",
        "retries", "retry_backoff_seconds", "host_delay_seconds", "min_page_text_chars", "min_pdf_text_chars",
        "evidence_first_bytes", "pilot_units", "progress_seconds", "ceiling_requests", "ceiling_wall_seconds",
        "allowlist", "never_retry", "targets")
MODES = ("on_entry", "doc_entry", "doc_many")
CC_RE = re.compile(rb"creativecommons\.org/licenses/([a-z\-]+)/([0-9.]+)", re.I)


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in NEED if k not in cfg]
    if missing:
        raise SystemExit(f"FATAL: {path} lacks {missing}")
    for t in cfg["targets"]:
        if t.get("mode") not in MODES or not t.get("entry") or not (t.get("urls") or t.get("discover")):
            raise SystemExit(f"FATAL: target {t!r} needs `entry`, a `mode` in {MODES}, and `urls` or `discover`")
        if not t.get("licence") or not t.get("licence_basis"):
            raise SystemExit(f"FATAL: target {t['entry']} states no licence and basis; the stub needs both")
    return cfg


def unit_key(target: dict) -> str:
    return hashlib.sha256(json.dumps([FETCH_VERSION, target], sort_keys=True).encode()).hexdigest()


class RobotsHttp:
    """squiddy's robots reader asks `http.get(url, accept)` for a requests-like response. This hands it SEL-036's
    client, so the robots read obeys the same allowlist on every hop; a refused or failed read answers None with the
    reason in `log`, which squiddy reads as a transport error (RFC 9309 2.3.1.4: unreachable, disallow all)."""

    def __init__(self, net):
        self.net, self.log = net, []

    def get(self, url, accept=None):
        r = self.net.get(url, accept=accept)
        if r.error:
            self.log.append({"error": r.error, "refused_host": r.refused_host})
            return None
        return types.SimpleNamespace(status_code=r.status, content=r.body, history=[], reason=None, headers=r.headers)


class FakeRobots:
    """The test stand-in's robots reading: every path allowed, no request."""

    def check(self, url, http, routes=None):
        return True, {"robots_url": url, "decision": "fake", "allowed": True}


def robots_check(obs, rhttp, url: str) -> tuple[bool, dict]:
    """(may_fetch, robots_row). A host off the Network line is never asked, not even for its robots.txt. A robots.txt
    that REDIRECTS to a host off the Network line was never read: squiddy's reader sees a transport failure and
    answers disallow-all (RFC 9309 2.3.1.4), which is true of what this run may do but says nothing of the host. The
    row then names the hop (`why: off_allowlist:<hop host>`), so the posture recorded is this task's Network line,
    never a robots refusal the host did not make."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if rhttp is not None and host not in rhttp.net.allow:
        return False, {"robots_url": None, "decision": "not_asked", "allowed": False, "why": f"off_allowlist:{host}"}
    may, row = obs.check(url, rhttp)
    if not may and str(row.get("error") or "").startswith("off_allowlist:"):
        row = {**row, "why": row["error"], "robots_hop_off_allowlist": True}
    return may, row


def refused_posture(robots: dict, host: str) -> dict:
    """The posture of a URL the robots step stopped: the Network line's refusal, or the host's robots rule."""
    why = str(robots.get("why") or "")
    if why.startswith("off_allowlist:"):
        return {"posture": "off_allowlist", "host": why.split(":", 1)[1], "at": R.now(), "status": None,
                "first_bytes": "", "error": why, "robots": robots}
    return {"posture": "robots_disallowed", "host": host, "at": R.now(), "status": robots.get("status"),
            "first_bytes": "", "error": None, "robots": robots}


def text_ok(rec: dict, target: dict, root: Path, cfg: dict) -> tuple[bool, str, dict]:
    """Is the held text the work, and enough of it? Returns (ok, why, facts)."""
    from squiddy.acquire import UnreadablePdf, text_chars
    path = root / rec["text_path"].removeprefix("archive:")
    try:
        pages, chars = text_chars(path)
    except UnreadablePdf as exc:
        return False, f"unreadable: {exc}", {}
    facts = {"pages": pages, "text_chars": chars}
    is_pdf = rec["raw_path"] == rec["text_path"]
    floor = int(cfg["min_pdf_text_chars"] if is_pdf else cfg["min_page_text_chars"])
    if chars < floor:
        return False, f"{chars} characters, under the {floor} floor", facts
    if target.get("min_pages") and pages < int(target["min_pages"]):
        return False, f"{pages} pages, under the {target['min_pages']} the work has: not the work", facts
    if target.get("expect"):
        from squiddy import pdftext
        body = "\n".join(pdftext.page_texts(path)) if is_pdf else path.read_text(encoding="utf-8", errors="replace")
        if not re.search(target["expect"], body, re.I):
            return False, f"the text does not carry {target['expect']!r}: not the work", facts
    raw = (root / rec["raw_path"].removeprefix("archive:")).read_bytes()
    found = sorted({f"CC {m.group(1).decode().upper()} {m.group(2).decode()}" for m in CC_RE.finditer(raw)})
    if is_pdf and not found:
        from squiddy import pdftext
        found = sorted({f"CC {m.group(1).upper()} {m.group(2)}" for m in
                        re.finditer(r"creativecommons\.org/licenses/([a-z\-]+)/([0-9.]+)",
                                    "\n".join(pdftext.page_texts(path)), re.I)})
    facts["licence_found"] = found
    return True, "text taken", facts


def discover(target: dict, net, obs, rhttp, cfg: dict, steps: list) -> list[str]:
    d = target["discover"]
    may, robots = robots_check(obs, rhttp, d["page"])
    step = {"url": d["page"], "role": "discovery", "robots": robots}
    steps.append(step)
    if not may:
        step["posture"] = refused_posture(robots, urllib.parse.urlsplit(d["page"]).hostname)
        return []
    r = net.get(d["page"])
    step["posture"] = R.posture(r, cfg)
    if r.status != 200:
        return []
    body = r.body.decode("utf-8", "replace").replace("\\/", "/")
    links = []
    for m in re.finditer(d["link"], body):
        # `template`: the link is built from the match's first group (a path in a JSON listing, not a URL)
        found = d["template"].replace("{0}", m.group(1)) if d.get("template") else m.group(0)
        u = urllib.parse.urljoin(r.final_url, found)
        if d.get("rewrite"):
            u = u.replace(d["rewrite"][0], d["rewrite"][1])
        if target.get("exclude_link") and re.search(target["exclude_link"], u):
            continue
        if u not in links:
            links.append(u)
    step["links_found"] = links
    return links


def fetch_one(target: dict, url: str, net, obs, rhttp, cfg: dict, root: Path, seed_id: str, steps: list) -> dict | None:
    """One URL: refused before asking when the task forbids its host, robots read, then SEL-036's snapshot."""
    host = urllib.parse.urlsplit(url).hostname or ""
    step = {"url": url, "role": "text"}
    steps.append(step)
    if host in cfg["never_retry"]:
        step["posture"] = {"posture": "not_retried", "host": host, "at": R.now(),
                           "why": "the task forbids asking this host again (SEL-036 drew HTTP 403)"}
        return None
    may, robots = robots_check(obs, rhttp, url)
    step["robots"] = robots
    if not may:
        step["posture"] = refused_posture(robots, host)
        return None
    rec = R.fetch({"id": seed_id}, url, net, cfg, root)
    step.update({k: rec.get(k) for k in ("final_url", "status", "posture")})
    if rec.get("acquisition") != "auto":
        return None
    ok, why, facts = text_ok(rec, target, root, cfg)
    step.update({"check": why, **facts})
    if not ok:
        step["posture"] = {**rec["posture"], "posture": "rejected"}
        return None
    return {**rec, **facts}


def run_unit(target: dict, net, obs, rhttp, cfg: dict, root: Path) -> dict:
    steps: list = []
    got: list = []
    if target["mode"] == "doc_many":
        for u in discover(target, net, obs, rhttp, cfg, steps):
            # the id is the page's path below the listed directory: two sections may hold a file of one name
            path = urllib.parse.urlsplit(u).path
            below = path.split(target["id_below"], 1)[1] if target.get("id_below") in path else Path(path).name
            stem = re.sub(r"[^a-z0-9]+", "_", below.rsplit(".", 1)[0].lower()).strip("_")
            rec = fetch_one(target, u, net, obs, rhttp, cfg, root, f"{target['new_prefix']}{stem}", steps)
            if rec:
                got.append({**rec, "new_id": f"{target['new_prefix']}{stem}", "page_url": u})
    else:
        # every discovered link is a candidate, in page order: the first whose text passes the checks is the work
        urls = list(target.get("urls") or []) or discover(target, net, obs, rhttp, cfg, steps)
        for u in urls:
            rec = fetch_one(target, u, net, obs, rhttp, cfg, root, target["entry"], steps)
            if rec:
                got.append({**rec, "page_url": u})
                break
    outcome = "acquired" if got else "manual"
    last = next((s for s in reversed(steps) if s.get("posture")), None)
    return {"outcome": outcome, "steps": steps, "got": got,
            "manual_posture": None if got else (last or {}).get("posture")}


def plan(cfg: dict) -> list[dict]:
    return [{"entry": t["entry"], "target": t, "key": unit_key(t)} for t in cfg["targets"]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=HERE / "sel037.yaml")
    ap.add_argument("--graph", type=Path, default=ROOT / "graphs/seldon-biblio")
    ap.add_argument("--checkpoint", type=Path, help="override the config's checkpoint (tests)")
    ap.add_argument("--only", help="comma-separated entry ids (a pilot by hand)")
    ap.add_argument("--plan", action="store_true", help="print the units and stop; no request")
    ap.add_argument("--fake-sleep-s", type=float, default=None, help="the test stand-in for the network")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    ck = a.checkpoint or (ROOT / cfg["checkpoint"])
    units = plan(cfg)
    if a.only:
        keep = set(a.only.split(","))
        units = [u for u in units if u["entry"] in keep]
    if a.plan:
        for u in units:
            print(u["entry"], u["target"]["mode"], u["target"].get("urls") or u["target"]["discover"]["page"])
        print(f"{len(units)} units planned")
        return 0
    if a.fake_sleep_s is not None:
        net, root = R.FakeNet(cfg, a.fake_sleep_s, ck.parent / "calls.txt"), ck.parent / "archive"
        root.mkdir(parents=True, exist_ok=True)
        log, obs, rhttp = ck.parent / "progress.txt", FakeRobots(), None
    else:
        from squiddy import posture
        net, root, log = R.Net(cfg), R.archive_root(a.graph), ROOT / cfg["log"]
        rhttp = RobotsHttp(net)
        obs = posture.observer(rhttp, cfg["user_agent"])
    done = R.load_done(ck)
    prog = R.Progress(log, len(units))
    prog.done = sum(1 for u in units if u["key"] in done)
    prog.say(f"start: {len(done)} rows in {ck}", force=True, requests=net.requests_made)
    t0, fresh, pilot_reported = time.time(), 0, len(done) > 0
    for u in units:
        if u["key"] in done:
            continue
        if net.requests_made >= int(cfg["ceiling_requests"]):
            prog.say("ceiling_requests reached; stopping", force=True, requests=net.requests_made)
            return 3
        if time.time() - t0 >= float(cfg["ceiling_wall_seconds"]):
            prog.say("ceiling_wall_seconds reached; stopping", force=True, requests=net.requests_made)
            return 3
        row = {"key": u["key"], "entry": u["entry"], "fetcher": FETCH_VERSION, "target": u["target"], "at": R.now()}
        try:
            if a.fake_sleep_s is not None:
                r = net.get((u["target"].get("urls") or [u["target"]["discover"]["page"]])[0])
                row.update({"outcome": "acquired" if r.status == 200 else "manual", "steps": [{"url": r.url}],
                            "got": []})
            else:
                row.update(run_unit(u["target"], net, obs, rhttp, cfg, root))
        except Exception as exc:                   # a failure is a row (section 15.7), and it is named
            row.update({"error": f"{type(exc).__name__}: {exc}"[:400], "outcome": "error"})
            prog.failed += 1
        R.append(ck, row)
        done[u["key"]] = row
        prog.done += 1
        fresh += 1
        prog.say(f"{u['entry']}: {row['outcome']}", force=True, requests=net.requests_made)
        if not pilot_reported and fresh >= int(cfg["pilot_units"]):
            per = (time.time() - t0) / fresh
            prog.say(f"PILOT: {fresh} units in {time.time() - t0:.1f}s, {per:.2f}s/unit; projected "
                     f"{per * len(units):.0f}s for {len(units)} units", force=True, requests=net.requests_made)
            pilot_reported = True
    prog.say("finished", force=True, requests=net.requests_made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
