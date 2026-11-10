"""SEL-036 Parts B and C: resolve every seed through its authorities, and snapshot every open documentation page.

    <squiddy venv>/bin/python scripts/sel036/resolve.py            # run, or resume: the same command
    <squiddy venv>/bin/python scripts/sel036/resolve.py --plan     # the units, no request

Run from the seldon checkout's root, with squiddy's interpreter (the confirmation measure is squiddy's own,
`squiddy.acquire.title_similarity`, imported, not copied). Every tunable is in scripts/sel036/sel036.yaml.

**Why a script and not squiddy's acquire.** squiddy acquire resolves a work BY ITS IDENTIFIER (Crossref, OpenAlex) and
fetches its open-access PDF; it is what admits these entries (Part D), and it runs over the catalog this script
writes. What it does not do is the task's Part B: find the identifier of a work the citing note names only by author,
year and title, through five authorities in a fixed order, keeping every attempt. That is a title search, and squiddy
holds a title search to a floor (`acquire.BY_TITLE_SEARCH`, `title_match_floor`); this script applies the same
measure at the same floor. Nor does acquire snapshot a documentation page (its `software` kind is metadata only,
"software_not_a_document"); Part C asks for the pages, so this script fetches them and the catalog admits each as a
`work` whose text is the held snapshot.

**Checkpointing (~/GitHub/CLAUDE.md section 15; the pattern of scripts/sel014r_replay_with_the_model.py):**

- **Unit of work:** one authority asked about one seed (`resolve`), or one page fetched (`fetch`).
- **Key:** sha256 of (phase, seed id, authority or URL, the seed's own fields, RESOLVER_VERSION). A changed seed or a
  changed resolver is a new key, so a stale answer is never reused.
- **Checkpoint:** one JSON line per finished unit in `checkpoint`, flushed and fsynced before the next unit starts.
  Re-running the command is the resume: completed keys are skipped, and a seed already confirmed asks no later
  authority.
- **Progress:** every `progress_seconds` and at each unit, to stdout and `log`: units done of planned, requests,
  rate, ETA, failures.
- **Pilot:** the first `pilot_units` units of a fresh checkpoint; their measured seconds per unit times the units
  planned is printed as the projection before the run continues.
- **Ceilings:** `ceiling_requests` and `ceiling_wall_seconds` stop new units; the run exits 3 naming the ceiling.
  Partial results stay usable: the catalog builder reads whatever the checkpoint holds and states its n.
- **Failures are rows:** a unit that raises is recorded with its error, and the next unit runs.

`--fake-sleep-s S` replaces the network with a deterministic stand-in that answers every request with a canned
record after sleeping S seconds and appends the URL to `<checkpoint dir>/calls.txt`; it exists for
tests/test_sel036_resolve_checkpoint.py, which SIGKILLs a run mid-loop and resumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import html.parser
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import yaml

#: Bumped when a resolver's query, parse or confirmation rule changes: every key changes with it.
RESOLVER_VERSION = "sel036-resolve/2"   # 2: the confirmation rule amended after the first run's audit (confirm())
#: The fetch units' own version: 2 writes the text derivative as the form-feed `.txt` squiddy reads (fetch/1 wrote `.md`,
#: which squiddy's acquire quarantined as an unreadable PDF on the first build).
FETCH_VERSION = "sel036-fetch/2"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


# ------------------------------------------------------------------------------------------------- configuration

def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    need = ("seeds", "checkpoint", "log", "archive_raw_dir", "archive_text_dir", "user_agent", "timeout_seconds",
            "max_redirects", "retries", "retry_backoff_seconds", "host_delay_seconds", "allowlist", "authorities",
            "title_floor", "year_tolerance", "search_rows", "min_page_text_chars", "evidence_first_bytes",
            "pilot_units", "progress_seconds", "ceiling_requests", "ceiling_wall_seconds")
    missing = [k for k in need if k not in cfg]
    if missing:
        raise SystemExit(f"FATAL: {path} lacks {missing}")
    return cfg


def archive_root(graph_dir: Path) -> Path:
    """The graph's declared archive root (graph.yaml `archive.root`), expanded as squiddy's `held` expands it."""
    spec = yaml.safe_load((graph_dir / "graph.yaml").read_text(encoding="utf-8"))
    raw = ((spec.get("archive") or {}).get("root"))
    if not raw:
        raise SystemExit(f"FATAL: {graph_dir}/graph.yaml declares no archive.root; the held bytes have nowhere to go")
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not p.is_dir():
        raise SystemExit(f"FATAL: archive root {p} (graph.yaml archive.root {raw!r}) is not a directory")
    return p


# ------------------------------------------------------------------------------------------------- checkpoint

def load_done(path: Path) -> dict:
    """The finished units by key. A unit whose row is a FAILURE (`error`) is not finished: its row stays in the file
    as the record of that attempt, and the next run asks again, once per run (the bounded retry of section 15.7).
    A later success for the same key supersedes it."""
    done = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue                      # a line torn by a kill: the unit is simply re-run
                if row.get("error"):
                    continue
                done[row["key"]] = row
    return done


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def unit_key(*parts) -> str:
    return hashlib.sha256(json.dumps([RESOLVER_VERSION, *parts], sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------- network

class Resp:
    def __init__(self, url, status=None, final_url=None, headers=None, body=b"", error=None, refused_host=None):
        self.url, self.status, self.final_url = url, status, final_url or url
        self.headers, self.body, self.error, self.refused_host = headers or {}, body, error, refused_host

    def record(self, first_bytes: int, keep_body: bool = False) -> dict:
        out = {"url": self.url, "status": self.status, "final_url": self.final_url, "error": self.error,
               "refused_host": self.refused_host, "content_type": self.headers.get("content-type"),
               "at": now()}
        if self.status != 200 or keep_body:
            out["first_bytes"] = self.body[:first_bytes].decode("utf-8", "replace")
        return out

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Net:
    """GET with the allowlist checked on every hop (redirects followed by hand), a per-host delay, and bounded retries
    on 429 and 5xx. Counts every request it makes."""

    def __init__(self, cfg: dict):
        import requests
        self.cfg, self.requests_made = cfg, 0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = cfg["user_agent"]
        self.allow = set(cfg["allowlist"])
        self.last: dict = {}

    def _wait(self, host: str) -> None:
        d = self.cfg["host_delay_seconds"]
        gap = float(d.get(host, d["default"]))
        t = self.last.get(host)
        if t is not None and time.time() - t < gap:
            time.sleep(gap - (time.time() - t))
        self.last[host] = time.time()

    def get(self, url: str, accept: str | None = None) -> Resp:
        import requests
        cur = url
        for _ in range(int(self.cfg["max_redirects"]) + 1):
            host = urllib.parse.urlsplit(cur).hostname or ""
            if host not in self.allow:
                return Resp(url, final_url=cur, error=f"off_allowlist:{host}", refused_host=host)
            r = None
            for attempt in range(int(self.cfg["retries"]) + 1):
                self._wait(host)
                self.requests_made += 1
                try:
                    r = self.s.get(cur, allow_redirects=False, timeout=float(self.cfg["timeout_seconds"]),
                                   headers={"Accept": accept} if accept else None)
                except requests.RequestException as exc:
                    if attempt == int(self.cfg["retries"]):
                        return Resp(url, final_url=cur, error=f"{type(exc).__name__}: {exc}"[:300])
                    time.sleep(float(self.cfg["retry_backoff_seconds"]) * 2 ** attempt)
                    continue
                if r.status_code in (429, 500, 502, 503, 504) and attempt < int(self.cfg["retries"]):
                    time.sleep(float(self.cfg["retry_backoff_seconds"]) * 2 ** attempt)
                    continue
                break
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                cur = urllib.parse.urljoin(cur, r.headers["location"])
                continue
            return Resp(url, status=r.status_code, final_url=cur,
                        headers={k.lower(): v for k, v in r.headers.items()}, body=r.content)
        return Resp(url, final_url=cur, error="too_many_redirects")


class FakeNet:
    """The test stand-in: every request sleeps, is logged to calls.txt (fsynced), and answers one canned record."""

    def __init__(self, cfg: dict, sleep_s: float, calls: Path):
        self.cfg, self.sleep_s, self.calls, self.requests_made = cfg, sleep_s, calls, 0

    def get(self, url: str, accept: str | None = None) -> Resp:
        self.requests_made += 1
        with self.calls.open("a", encoding="utf-8") as fh:
            fh.write(url + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        time.sleep(self.sleep_s)
        q = urllib.parse.urlsplit(url)
        title = urllib.parse.parse_qs(q.query).get("search", ["fake title"])[0]
        body = json.dumps({"results": [{"id": "https://openalex.org/W1", "display_name": title,
                                        "publication_year": 2000, "authorships": [], "doi": None}]}).encode()
        return Resp(url, status=200, headers={"content-type": "application/json"}, body=body)


# ------------------------------------------------------------------------------------------------- parsing helpers

def norm_doi(d: str | None) -> str | None:
    if not d:
        return None
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", str(d).strip(), flags=re.I)
    return d.lower() or None


def first_year(*vals) -> int | None:
    for v in vals:
        if v:
            m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(v))
            if m:
                return int(m.group(1))
    return None


def openalex_answer(w: dict) -> dict:
    loc = w.get("best_oa_location") or {}
    src = ((w.get("primary_location") or {}).get("source") or {})
    return {"title": w.get("display_name") or w.get("title"), "year": w.get("publication_year"),
            "authors": [a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])
                        if a.get("author", {}).get("display_name")],
            "venue": src.get("display_name"), "publisher": src.get("host_organization_name"),
            "doi": norm_doi(w.get("doi")), "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1] or None,
            "type": w.get("type"), "is_oa": (w.get("open_access") or {}).get("is_oa"),
            "oa_pdf_url": loc.get("pdf_url"), "oa_landing_url": loc.get("landing_page_url"),
            "licence": loc.get("license"), "arxiv_id": _arxiv_of(w)}


def _arxiv_of(w: dict) -> str | None:
    for loc in w.get("locations") or []:
        u = (loc.get("landing_page_url") or "") + " " + (loc.get("pdf_url") or "")
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", u)
        if m:
            return m.group(1)
    m = re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", w.get("doi") or "", re.I)
    return m.group(1) if m else None


def crossref_answer(m: dict) -> dict:
    title = (m.get("title") or [None])[0]
    if m.get("subtitle"):
        title = f"{title}: {m['subtitle'][0]}" if title else m["subtitle"][0]
    parts = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
    lic = (m.get("license") or [{}])[0]
    return {"title": title, "year": parts[0] if parts else None,
            "authors": [" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name")
                        for a in (m.get("author") or m.get("editor") or [])],
            "venue": (m.get("container-title") or [None])[0], "publisher": m.get("publisher"),
            "doi": norm_doi(m.get("DOI")), "type": m.get("type"), "isbn": m.get("ISBN"),
            "licence_url": lic.get("URL"), "url": m.get("URL")}


def csl_answer(c: dict) -> dict:
    parts = ((c.get("issued") or {}).get("date-parts") or [[None]])[0]
    return {"title": c.get("title"), "year": parts[0] if parts else None,
            "authors": [" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("literal")
                        for a in (c.get("author") or [])],
            "venue": c.get("container-title"), "publisher": c.get("publisher"), "doi": norm_doi(c.get("DOI")),
            "type": c.get("type"), "isbn": c.get("ISBN"), "url": c.get("URL")}


def s2_answer(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    pdf = p.get("openAccessPdf") or {}
    return {"title": p.get("title"), "year": p.get("year"), "authors": [a.get("name") for a in p.get("authors") or []],
            "venue": p.get("venue"), "doi": norm_doi(ext.get("DOI")), "arxiv_id": ext.get("ArXiv"),
            "s2_id": p.get("paperId"), "is_oa": p.get("isOpenAccess"), "oa_pdf_url": pdf.get("url") or None,
            "licence": pdf.get("license")}


def arxiv_atom_answer(xml: str) -> dict | None:
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(xml)
    e = root.find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return None
    eid = (e.findtext("a:id", default="", namespaces=ns) or "")
    m = re.search(r"abs/(\d{4}\.\d{4,5})(v\d+)?", eid)
    lic = None
    for link in e.findall("a:link", ns):
        if "license" in (link.get("rel") or ""):
            lic = link.get("href")
    return {"title": " ".join((e.findtext("a:title", namespaces=ns) or "").split()),
            "year": first_year(e.findtext("a:published", namespaces=ns)),
            "authors": [a.findtext("a:name", namespaces=ns) for a in e.findall("a:author", ns)],
            "arxiv_id": m.group(1) if m else None, "version": m.group(2) if m and m.group(2) else None,
            "doi": norm_doi(e.findtext("x:doi", namespaces=ns)) or (f"10.48550/arxiv.{m.group(1)}" if m else None),
            "venue": "arXiv", "licence_url": lic, "is_oa": True,
            "oa_pdf_url": f"https://arxiv.org/pdf/{m.group(1)}" if m else None,
            "url": f"https://arxiv.org/abs/{m.group(1)}" if m else None}


class _Text(html.parser.HTMLParser):
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "pre", "section", "article", "td"}
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self._in_title, self.scripts = [], 0, "", False, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            self.scripts += tag == "script"
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def html_text(body: bytes) -> tuple[str, str, int]:
    """(visible text, page title, script tags) of an HTML page; stdlib only."""
    p = _Text()
    p.feed(body.decode("utf-8", "replace"))
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, " ".join(p.title.split()), p.scripts


def page_title(body: bytes) -> str:
    m = re.search(rb"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    return html.unescape(" ".join(m.group(1).decode("utf-8", "replace").split())) if m else ""


# ------------------------------------------------------------------------------------------------- authorities

def _fold(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def surnames_agree(seed: dict, ans: dict) -> bool | None:
    """Whether a cited author's surname is among the answer's authors (accent- and case-folded, as a substring of
    the full name). None when either side names no person."""
    cited = [_fold(str(a)).split()[-1] for a in seed.get("authors") or [] if str(a).strip()]
    got = " | ".join(_fold(str(a)) for a in ans.get("authors") or [] if a)
    if not cited or not got:
        return None
    return any(re.search(rf"\b{re.escape(c)}\b", got) for c in cited)


def confirm(seed: dict, ans: dict | None, cfg: dict, by_search: bool = False) -> tuple[bool, float | None, str]:
    """The confirmation rule, pre-registered in sel036.yaml (rev 2, after the first run's audit; see RESOLVER_VERSION).

    1. A seed whose title IS its identifier (`arXiv:...`, `doi:...`) is confirmed by the identifier.
    2. squiddy's title measure (`squiddy.acquire.title_similarity`) at the graph's floor, and the year within the
       tolerance, for every answer.
    3. An answer found by a TITLE SEARCH (not by the seed's own identifier) must also
       a. carry the DOI or arXiv id the citing note states, when it states one: a search never overrides the note's
          own identifier (sel036 audit: a Crossref search answered an ICKG paper for arXiv:2403.07311);
       b. share a cited author's surname, when both sides name people (record linkage on more than one field:
          Fellegi and Sunter 1969; squiddy biblio's person match keys). A WORK whose title is token-identical and whose
          year agrees is kept on a surname disagreement, with the disagreement in `why` (the citing note can misname
          the author: cc5 cites "Adler et al." for Saeedi, Peukert and Rahm's ESWC 2020 paper). Grey literature has
          no such exception: its short titles are exactly where a scholarly index matched the wrong work (sel036
          audit: NIOSH "Hierarchy of Controls" to a 2003 nursing editorial).
    """
    if not ans or not ans.get("title"):
        return False, None, "no record"
    from squiddy.acquire import title_similarity, title_tokens
    t = str(seed.get("title") or "")
    if re.match(r"^(arxiv|doi):", t, re.I):
        want = t.split(":", 1)[1].strip().lower()
        got = {str(ans.get("arxiv_id") or "").lower(), str(ans.get("doi") or "").lower()}
        ok = want in got or f"10.48550/arxiv.{want}" in got
        return ok, None, "identifier " + ("matches" if ok else f"does not match ({sorted(got)})")
    sim = round(title_similarity(ans["title"], t), 3)
    if sim < float(cfg["title_floor"]):
        return False, sim, f"title similarity {sim} under the floor {cfg['title_floor']}"
    sy, ay = seed.get("year"), ans.get("year")
    if sy and ay and abs(int(sy) - int(ay)) > int(cfg["year_tolerance"]):
        return False, sim, f"year {ay} is not the cited {sy} (tolerance {cfg['year_tolerance']})"
    why = f"title similarity {sim}" + (f", year {ay}" if ay else "")
    if by_search:
        sd, sa = norm_doi(seed.get("doi")), str(seed.get("arxiv") or "").lower()
        if sd or sa:
            got = {str(ans.get("doi") or "").lower(), str(ans.get("arxiv_id") or "").lower()}
            if not (sd in got or sa in got or (sa and f"10.48550/arxiv.{sa}" in got)):
                return False, sim, f"a title search answered {sorted(x for x in got if x)}, not the cited {sd or sa}"
        agree = surnames_agree(seed, ans)
        exact = title_tokens(ans["title"]) == title_tokens(t)
        if agree is False:
            if seed["kind"] == "work" and exact and sy and ay:
                why += f"; DISCREPANCY: the cited authors {seed.get('authors')} are not the record's {ans.get('authors')}"
            else:
                return False, sim, f"no cited author ({seed.get('authors')}) among the record's {ans.get('authors')}"
        elif agree is None and seed.get("authors") and not exact:
            return False, sim, "the record names no author and its title is not the cited one exactly"
    return True, sim, why


def best(seed: dict, answers: list[dict], cfg: dict) -> tuple[dict | None, bool, float | None, str]:
    """The best-confirming answer of a SEARCH, else the most similar one (kept as evidence)."""
    scored = [(a, *confirm(seed, a, cfg, by_search=True)) for a in answers]
    if not scored:
        return None, False, None, "no record"
    scored.sort(key=lambda x: (x[1], x[2] or 0), reverse=True)
    return scored[0]


def known(seed: dict, prior: list[dict]) -> dict:
    """The identifiers a seed states, plus those an earlier authority's CONFIRMED answer gave (never an unconfirmed
    one: a near miss must not steer the next authority)."""
    ids = {"doi": norm_doi(seed.get("doi")), "arxiv": seed.get("arxiv")}
    for row in prior:
        if row.get("confirmed") and row.get("answer"):
            ids["doi"] = ids["doi"] or row["answer"].get("doi")
            ids["arxiv"] = ids["arxiv"] or row["answer"].get("arxiv_id")
    return ids


def ask(authority: str, seed: dict, prior: list[dict], net, cfg: dict) -> dict:
    """One authority about one seed: {queries, answer, confirmed, similarity, why}."""
    kind, ids, fb = seed["kind"], known(seed, prior), int(cfg["evidence_first_bytes"])
    rows = int(cfg["search_rows"])
    q: list[dict] = []
    title = str(seed.get("title") or "")
    is_id_title = bool(re.match(r"^(arxiv|doi):", title, re.I))

    def done(ans, why_none="no record"):
        if ans is None:
            return {"queries": q, "answer": None, "confirmed": False, "similarity": None, "why": why_none}
        ok, sim, why = confirm(seed, ans, cfg)
        return {"queries": q, "answer": ans, "confirmed": ok, "similarity": sim, "why": why}

    def get(url, accept=None):
        r = net.get(url, accept)
        q.append(r.record(fb))
        return r

    scholarly = kind in ("work", "grey") or ids["doi"]
    if authority in ("openalex", "crossref", "semanticscholar", "doi") and not scholarly:
        return {"queries": [], "answer": None, "confirmed": False, "similarity": None,
                "why": f"not_applicable: a {kind} with no DOI is not a scholarly work this index holds"}

    if authority == "openalex":
        if ids["doi"] or ids["arxiv"]:
            d = ids["doi"] or f"10.48550/arxiv.{ids['arxiv']}"
            r = get(f"https://api.openalex.org/works/doi:{urllib.parse.quote(d, safe='/')}")
            return done(openalex_answer(r.json()) if r.status == 200 else None)
        r = get("https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": title, "per-page": rows}))
        if r.status != 200:
            return done(None)
        a, ok, sim, why = best(seed, [openalex_answer(w) for w in r.json().get("results") or []], cfg)
        return {"queries": q, "answer": a, "confirmed": ok, "similarity": sim, "why": why}

    if authority == "crossref":
        if ids["doi"]:
            r = get(f"https://api.crossref.org/works/{urllib.parse.quote(ids['doi'], safe='/')}")
            return done(crossref_answer(r.json()["message"]) if r.status == 200 else None)
        if is_id_title:
            return done(None, "not_applicable: the seed's only identifier is an arXiv id (DataCite, not Crossref)")
        bib = " ".join(str(x) for x in [title, *(seed.get("authors") or [])[:2], seed.get("year") or ""] if x)
        r = get("https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": bib, "rows": rows}))
        if r.status != 200:
            return done(None)
        a, ok, sim, why = best(seed, [crossref_answer(m) for m in r.json()["message"].get("items") or []], cfg)
        return {"queries": q, "answer": a, "confirmed": ok, "similarity": sim, "why": why}

    if authority == "doi":
        if not ids["doi"]:
            return done(None, "not_applicable: no DOI is known for this seed")
        r = get(f"https://doi.org/{urllib.parse.quote(ids['doi'], safe='/')}",
                accept="application/vnd.citationstyles.csl+json")
        if r.status == 200 and "json" in (r.headers.get("content-type") or ""):
            return done(csl_answer(r.json()))
        return done(None, f"doi.org content negotiation: {r.error or r.status}")

    if authority == "semanticscholar":
        fields = "title,authors,year,venue,externalIds,isOpenAccess,openAccessPdf"
        if ids["doi"] or ids["arxiv"]:
            pid = f"DOI:{ids['doi']}" if ids["doi"] else f"ARXIV:{ids['arxiv']}"
            r = get(f"https://api.semanticscholar.org/graph/v1/paper/{urllib.parse.quote(pid, safe=':/')}?fields={fields}")
            return done(s2_answer(r.json()) if r.status == 200 else None)
        r = get("https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
            {"query": title, "limit": rows, "fields": fields}))
        if r.status != 200:
            return done(None)
        a, ok, sim, why = best(seed, [s2_answer(p) for p in r.json().get("data") or []], cfg)
        return {"queries": q, "answer": a, "confirmed": ok, "similarity": sim, "why": why}

    if authority == "page":
        return page(seed, ids, net, cfg, q, get)
    raise SystemExit(f"FATAL: unknown authority {authority!r} (sel036.yaml authorities)")


LICENCE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def page(seed: dict, ids: dict, net, cfg: dict, q: list, get) -> dict:
    """The publisher's or project's own page: arXiv's export API, PyPI's JSON, the repository's release and licence
    file, or the seed's canonical URL. A refusal is recorded with its posture; it is an answer, not a crash."""
    if ids.get("arxiv"):
        r = get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": ids["arxiv"]}))
        ans = arxiv_atom_answer(r.body.decode("utf-8", "replace")) if r.status == 200 else None
        ok, sim, why = confirm(seed, ans, cfg) if ans else (False, None, "arXiv has no entry")
        return {"queries": q, "answer": ans, "confirmed": ok, "similarity": sim, "why": why}
    if seed["kind"] == "software":
        ans: dict = {"title": seed.get("title"), "url": seed.get("url"), "repository": seed.get("url")}
        why = []
        if seed.get("pypi"):
            r = get(f"https://pypi.org/pypi/{seed['pypi']}/json")
            if r.status == 200:
                info = r.json()["info"]
                lic_lines = (info.get("license") or "").strip().splitlines()
                ans.update({"version": info.get("version"), "licence": info.get("license_expression")
                            or (lic_lines[0][:80] if lic_lines else None),
                            "pypi": seed["pypi"], "summary": info.get("summary"),
                            "release_date": ((r.json().get("urls") or [{}])[0].get("upload_time_iso_8601"))})
                why.append(f"PyPI {seed['pypi']} {info.get('version')}")
        if seed.get("repo"):
            rp = get(f"https://github.com/{seed['repo']}")
            if rp.status == 200:
                why.append(f"GitHub repository {seed['repo']} HTTP 200")
            r = get(f"https://github.com/{seed['repo']}/releases/latest")
            m = re.search(r"/releases/tag/([^/?#]+)$", r.final_url or "")
            if r.status == 200 and m:
                ans["release_tag"] = urllib.parse.unquote(m.group(1))
                ans.setdefault("version", ans["release_tag"])
                if not ans.get("version"):
                    ans["version"] = ans["release_tag"]
                why.append(f"GitHub release {ans['release_tag']}")
            elif r.status == 200 or r.status == 404:
                why.append("GitHub: no release published")
            for name in LICENCE_FILES:
                lr = get(f"https://raw.githubusercontent.com/{seed['repo']}/HEAD/{name}")
                if lr.status == 200:
                    line = next((ln.strip() for ln in lr.body.decode("utf-8", "replace").splitlines() if ln.strip()), "")
                    ans["licence_file"] = name
                    ans["licence_file_first_line"] = line[:120]
                    ans["licence_file_sha256"] = hashlib.sha256(lr.body).hexdigest()
                    ans.setdefault("licence", None)
                    if not ans.get("licence"):
                        ans["licence"] = spdx_guess(lr.body.decode("utf-8", "replace"))
                    why.append(f"{name}: {line[:60]}")
                    break
        ok = bool(why) and any(x.startswith(("PyPI", "GitHub release", "GitHub repository", "LICENSE", "COPYING")) for x in why)
        if not ok and seed.get("url") and not seed.get("repo"):
            r = get(seed["url"])
            ok = r.status == 200
            why.append(f"page {r.error or r.status}")
        return {"queries": q, "answer": ans, "confirmed": ok, "similarity": None,
                "why": "; ".join(why) or "no project page answered"}
    url = seed.get("url") or (f"https://doi.org/{ids['doi']}" if ids.get("doi") else None)
    if not url:
        return {"queries": q, "answer": None, "confirmed": False, "similarity": None,
                "why": "no publisher or project page is known for this seed"}
    r = get(url)
    if r.status != 200:
        return {"queries": q, "answer": None, "confirmed": False, "similarity": None,
                "why": f"page {r.error or r.status}", "posture": posture(r, cfg)}
    pt = page_title(r.body)
    ans = {"title": pt or None, "url": r.final_url}
    num = str(seed.get("standard_number") or "")
    if seed["kind"] == "standard":
        # A standard's own page confirms it by its number (every digit group of three or more), or, for a number with
        # none (OMG's "SysML 2.0"), by the page's title at the title floor.
        token = re.findall(r"\d{3,}", num)
        by_num = bool(token) and all(t in r.body.decode("utf-8", "replace") for t in token)
        ok_t, sim, why_t = confirm(seed, ans, cfg)
        return {"queries": q, "answer": ans, "confirmed": by_num or ok_t, "similarity": sim,
                "why": f"page HTTP 200; " + (f"states {num}" if by_num else why_t)}
    ok, sim, why = confirm(seed, ans, cfg)
    return {"queries": q, "answer": ans, "confirmed": ok, "similarity": sim, "why": f"page HTTP 200; {why}"}


def spdx_guess(text: str) -> str | None:
    """The licence a LICENSE file's opening states, by its standard first words. A guess, recorded as one
    (`licence_basis: LICENSE file first line`); no file that matches none is labelled."""
    head = " ".join(text.split())[:400].lower()
    for needle, spdx in (("mit license", "MIT"), ("permission is hereby granted, free of charge", "MIT"),
                         ("apache license", "Apache-2.0"), ("bsd 3-clause", "BSD-3-Clause"),
                         ("redistribution and use in source and binary forms", "BSD"),
                         ("gnu general public license", "GPL"), ("gnu lesser general public license", "LGPL"),
                         ("mozilla public license", "MPL-2.0"), ("creative commons", "CC")):
        if needle in head:
            return spdx
    return None


def posture(r: Resp, cfg: dict) -> dict:
    """A host's answer to a scripted GET, as the access posture the manifest records (squiddy DN-055 R-240's
    vocabulary where it has one): the status, the response's first bytes, the time."""
    body = r.body or b""
    if r.refused_host:
        kind = "off_allowlist"
    elif r.error:
        kind = "unreachable"
    elif r.status in (401, 403, 429, 451) or (r.status == 503 and b"challenge" in body.lower()):
        kind = "bot_wall" if r.status != 401 else "login_required"
    elif r.status == 200:
        text, _t, scripts = html_text(body) if b"<html" in body[:2000].lower() else (body.decode("utf-8", "replace"), "", 0)
        kind = "javascript_only" if scripts and len(text) < int(cfg["min_page_text_chars"]) else "open"
    else:
        kind = f"http_{r.status}"
    return {"posture": kind, "status": r.status, "error": r.error, "host": urllib.parse.urlsplit(r.final_url).hostname,
            "first_bytes": body[: int(cfg["evidence_first_bytes"])].decode("utf-8", "replace"), "at": now()}


# ------------------------------------------------------------------------------------------------- fetch

#: A page whose path ends in one of these is already text (a README, a user guide): held as it came.
PLAIN_TEXT_SUFFIXES = (".md", ".rst", ".txt")


def fetch(seed: dict, url: str, net, cfg: dict, root: Path) -> dict:
    """Snapshot one documentation page under the archive root: the raw bytes and a text derivative."""
    r = net.get(url)
    rec = {"url": url, "final_url": r.final_url, "status": r.status, "posture": posture(r, cfg)}
    if r.status != 200 or rec["posture"]["posture"] != "open":
        rec["acquisition"] = "manual"
        return rec
    body = r.body
    raw_sha = hashlib.sha256(body).hexdigest()
    if body[:5] == b"%PDF-":
        # A PDF is held as it came; squiddy's parse stage reads it (its reader of record), so it is its own text.
        stem = f"{seed['id']}__{hashlib.sha256(url.encode()).hexdigest()[:10]}"
        raw_rel = f"{cfg['archive_raw_dir']}/{stem}.pdf"
        (root / raw_rel).parent.mkdir(parents=True, exist_ok=True)
        (root / raw_rel).write_bytes(body)
        rec.update({"acquisition": "auto", "raw_path": f"archive:{raw_rel}", "raw_sha256": raw_sha,
                    "bytes": len(body), "text_path": f"archive:{raw_rel}", "text_sha256": raw_sha, "text_chars": None,
                    "page_title": None, "content_type": r.headers.get("content-type"), "retrieved_at": now()})
        return rec
    plain = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower() in PLAIN_TEXT_SUFFIXES
    ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower() if plain else ".html"
    stem = f"{seed['id']}__{hashlib.sha256(url.encode()).hexdigest()[:10]}"
    raw_rel = f"{cfg['archive_raw_dir']}/{stem}{ext}"
    (root / raw_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / raw_rel).write_bytes(body)
    if plain:
        text, title = body.decode("utf-8", "replace"), ""
    else:
        text, title, _ = html_text(body)
    text_rel = f"{cfg['archive_text_dir']}/{stem}.txt"
    # squiddy reads two text forms, PDF and the form-feed `.txt` (squiddy docs/KIT_BOUNDARY.md; `pdftext.page_texts`);
    # the whole snapshot is one page. The provenance line is the text's first line, not a comment syntax.
    header = f"Snapshot of {url}, retrieved {now()}, sha256 {raw_sha}.\n\n"
    tbytes = (header + text + "\n").encode("utf-8")
    (root / text_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / text_rel).write_bytes(tbytes)
    rec.update({"acquisition": "auto", "raw_path": f"archive:{raw_rel}", "raw_sha256": raw_sha, "bytes": len(body),
                "text_path": f"archive:{text_rel}", "text_sha256": hashlib.sha256(tbytes).hexdigest(),
                "text_chars": len(text), "page_title": title or None, "content_type": r.headers.get("content-type"),
                "retrieved_at": now()})
    return rec


# ------------------------------------------------------------------------------------------------- the loop

def plan(seeds: list[dict], cfg: dict) -> list[dict]:
    """Every unit a full run could make, in order. A resolve unit after a confirming one is skipped at run time."""
    out = []
    for s in seeds:
        for a in cfg["authorities"]:
            out.append({"phase": "resolve", "seed": s["id"], "authority": a, "key": unit_key("resolve", s, a)})
    for s in seeds:
        urls = list(s.get("texts") or [])
        for u in urls:
            out.append({"phase": "fetch", "seed": s["id"], "url": u, "key": unit_key(FETCH_VERSION, s["id"], u)})
    return out


class Progress:
    def __init__(self, path: Path, total: int):
        self.path, self.total, self.t0, self.done, self.failed, self.last = path, total, time.time(), 0, 0, 0.0
        path.parent.mkdir(parents=True, exist_ok=True)

    def say(self, msg: str, force: bool = False, requests: int = 0, interval: float = 30) -> None:
        if not force and time.time() - self.last < interval:
            return
        self.last = time.time()
        el = time.time() - self.t0
        rate = self.done / el if el > 0 and self.done else 0.0
        eta = (self.total - self.done) / rate if rate else float("nan")
        line = (f"{now()} {self.done}/{self.total} units, {requests} requests, {self.failed} failed, "
                f"{rate:.2f} units/s, eta {eta:.0f}s :: {msg}")
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=HERE / "sel036.yaml")
    ap.add_argument("--graph", type=Path, default=ROOT / "graphs/seldon-biblio")
    ap.add_argument("--checkpoint", type=Path, help="override the config's checkpoint (tests)")
    ap.add_argument("--seeds", type=Path, help="override the config's seed file (tests)")
    ap.add_argument("--only", help="comma-separated seed ids (a pilot by hand)")
    ap.add_argument("--plan", action="store_true", help="print the units and stop; no request")
    ap.add_argument("--fake-sleep-s", type=float, default=None, help="the test stand-in for the network")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    ck = a.checkpoint or (ROOT / cfg["checkpoint"])
    seeds_path = a.seeds or (ROOT / cfg["seeds"])
    seeds = yaml.safe_load(seeds_path.read_text(encoding="utf-8"))["seeds"]
    if a.only:
        keep = set(a.only.split(","))
        seeds = [s for s in seeds if s["id"] in keep]
    units = plan(seeds, cfg)
    if a.plan:
        for u in units:
            print(u["phase"], u["seed"], u.get("authority") or u.get("url"))
        print(f"{len(units)} units planned")
        return 0
    if a.fake_sleep_s is not None:
        net, root = FakeNet(cfg, a.fake_sleep_s, ck.parent / "calls.txt"), ck.parent / "archive"
        root.mkdir(parents=True, exist_ok=True)
        log = ck.parent / "progress.txt"
    else:
        net, root, log = Net(cfg), archive_root(a.graph), ROOT / cfg["log"]
    done = load_done(ck)
    by_seed = {s["id"]: s for s in seeds}
    prog = Progress(log, len(units))
    prog.done = sum(1 for u in units if u["key"] in done)
    prog.say(f"start: {len(done)} rows in {ck}", force=True, requests=net.requests_made)
    t0, fresh, pilot_reported = time.time(), 0, len(done) > 0
    for u in units:
        if u["key"] in done:
            continue
        seed = by_seed[u["seed"]]
        if u["phase"] == "resolve":
            prior = [done[k["key"]] for k in units if k["phase"] == "resolve" and k["seed"] == u["seed"]
                     and k["key"] in done]
            if any(r.get("confirmed") for r in prior):
                continue                           # the chain ended at an earlier authority
        if net.requests_made >= int(cfg["ceiling_requests"]):
            prog.say("ceiling_requests reached; stopping", force=True, requests=net.requests_made)
            return 3
        if time.time() - t0 >= float(cfg["ceiling_wall_seconds"]):
            prog.say("ceiling_wall_seconds reached; stopping", force=True, requests=net.requests_made)
            return 3
        row = {"key": u["key"], "phase": u["phase"], "seed": u["seed"], "resolver": RESOLVER_VERSION, "at": now()}
        try:
            if u["phase"] == "resolve":
                row["authority"] = u["authority"]
                row.update(ask(u["authority"], seed, prior, net, cfg))
            else:
                row.update(fetch(seed, u["url"], net, cfg, root))
        except Exception as exc:                   # a failure is a row (section 15.7), and it is named
            row.update({"error": f"{type(exc).__name__}: {exc}"[:400], "confirmed": False})
            prog.failed += 1
        append(ck, row)
        done[u["key"]] = row
        prog.done += 1
        fresh += 1
        label = u.get("authority") or u.get("url")
        prog.say(f"{u['phase']} {u['seed']} {label}: {row.get('why') or row.get('acquisition') or row.get('error')}",
                 force=False, requests=net.requests_made, interval=float(cfg["progress_seconds"]))
        if not pilot_reported and fresh >= int(cfg["pilot_units"]):
            per = (time.time() - t0) / fresh
            prog.say(f"PILOT: {fresh} units in {time.time() - t0:.1f}s, {per:.2f}s/unit; projected "
                     f"{per * len(units):.0f}s for {len(units)} planned units (an upper bound: a confirmed seed asks "
                     f"no later authority)", force=True, requests=net.requests_made)
            pilot_reported = True
    prog.say("finished", force=True, requests=net.requests_made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
