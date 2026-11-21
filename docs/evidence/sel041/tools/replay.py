"""SEL-041 Part A: replay the last 30 merged tasks of a repository against three slice granularities and report the
share of the suite each would have selected. Read only.

Selection models (what a declared slice could say):
  G1  top-level directory: a change under the package directory selects the whole suite.
  G2  package sub-directory (seldon/core, seldon/commands, src/hazbrief/brief, ...): the test files whose import
      closure touches any module in that sub-directory.
  G3  module: the test files whose transitive import closure contains a changed module (static `import`/`from`
      statements, function-level imports included; Pants' dependency inference does the same for Python).
Every model: changed test files select themselves; documents and records (cc_tasks, handoffs, docs, the event store,
state, logs) select nothing; conftest.py, pyproject.toml and the lock select the whole suite (rule 4). A path no
category matches is counted `unmatched` and selects the whole suite (rule 4). Shares are by collected test count.
"""
import ast
import fnmatch
import json
import os
import sys
from collections import Counter, defaultdict

REPO, PKG_ROOT, PKG = sys.argv[1], sys.argv[2], sys.argv[3]   # e.g. seldon . seldon | hazbrief-mcp src hazbrief
ROOT = os.path.join("/Users/brock/GitHub", REPO)
counts = json.load(open(f"/tmp/sel041/collect_{REPO}.json"))
TOTAL = sum(counts.values())
NOTHING = ["cc_tasks/*", "handoffs/*", "docs/*", "seldon_events.jsonl", "state/*", "logs/*", "*.md", "evidence/*",
           "kit/ledger/*"]
FULL = ["tests/conftest.py", "pyproject.toml", "uv.lock", "requirements.txt", "conftest.py"]


def modname(path):
    rel = os.path.relpath(path, ROOT)
    if rel.startswith("tests/"):
        return "tests." + rel[6:-3].replace("/", ".")
    base = os.path.relpath(path, os.path.join(ROOT, PKG_ROOT))
    name = base[:-3].replace("/", ".")
    return name[:-9] if name.endswith(".__init__") else name


modules = {}
for top in (os.path.join(ROOT, PKG_ROOT, PKG), os.path.join(ROOT, "tests")):
    for d, _, files in os.walk(top):
        if "__pycache__" in d:
            continue
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(d, f)
                modules[modname(p)] = p

imports = defaultdict(set)
for name, path in modules.items():
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as exc:
        print("unparseable", path, exc, file=sys.stderr)
        continue
    pkg_parts = name.split(".")
    is_pkg = path.endswith("__init__.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports[name].add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - node.level + (1 if is_pkg else 0)]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            imports[name].add(mod)
            for a in node.names:
                imports[name].add(f"{mod}.{a.name}")


def resolve(m):
    """The known modules an import names: itself if known, and every package prefix (importing a.b.c runs a and a.b)."""
    out = set()
    parts = m.split(".")
    for i in range(1, len(parts) + 1):
        cand = ".".join(parts[:i])
        if cand in modules:
            out.add(cand)
    return out


closure_cache = {}


def closure(name):
    if name in closure_cache:
        return closure_cache[name]
    seen, stack = set(), [name]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for imp in imports.get(n, ()):
            stack.extend(resolve(imp) - seen)
    closure_cache[name] = seen
    return seen


conftest = closure("tests.conftest") if "tests.conftest" in modules else set()
test_files = {f: closure(modname(os.path.join(ROOT, f))) | conftest for f in counts}


def subdir(mod):
    parts = mod.split(".")
    return ".".join(parts[:2]) if len(parts) > 2 else parts[0]


def classify(path):
    if any(fnmatch.fnmatch(path, g) for g in FULL) or path.endswith("/conftest.py"):
        return "full"
    if path in counts:
        return "test"
    if path.startswith("tests/") and path.endswith(".py"):
        return "test_helper"
    if path.endswith(".py") and path.startswith(os.path.join(PKG_ROOT, PKG).lstrip("./") + "/"):
        return "code"
    if any(fnmatch.fnmatch(path, g) for g in NOTHING):
        return "nothing"
    return "unmatched"


def select(writes, model):
    sel, reasons = set(), set()
    for p in writes:
        c = classify(p)
        if c == "nothing":
            continue
        if c in ("full", "unmatched"):
            if CODE_ONLY:
                continue
            return set(counts), {f"{c}:{p}"}
        if c == "test":
            sel.add(p)
            continue
        mod = modname(os.path.join(ROOT, p))
        if model == "G1" and c == "code":
            return set(counts), {"G1"}
        if model == "G2" and c == "code":
            sd = subdir(mod)
            sel |= {f for f, cl in test_files.items() if any(m == sd or m.startswith(sd + ".") for m in cl)}
        else:
            sel |= {f for f, cl in test_files.items() if mod in cl}
    return sel, reasons


store = os.path.join(ROOT, "seldon_events.jsonl")
merges = []
CODE_ONLY = len(sys.argv) > 4
src_of = lambda e: e["payload"].get("source_file")
for line in open(store, encoding="utf-8", errors="replace"):
    if '"dispatch_finished"' not in line:
        continue
    e = json.loads(line)
    m = (e.get("payload") or {}).get("merge") or {}
    if m.get("commit") and e["payload"].get("base"):
        import subprocess
        d = subprocess.run(["git", "diff", "--name-only", e["payload"]["base"] + "..." + m["commit"]], cwd=ROOT,
                           capture_output=True, text=True)
        if d.returncode != 0:
            print("diff failed", src_of(e), d.stderr[:200], file=sys.stderr); continue
        merges.append((e["timestamp"], e["payload"]["source_file"], d.stdout.split()))
merges = merges[-30:]
rows, unmatched = [], Counter()
for ts, src, writes in merges:
    tops = Counter(p.split("/", 1)[0] if "/" in p else p for p in writes)
    shares = {}
    why = None
    for model in ("G1", "G2", "G3"):
        sel, reasons = select(writes, model)
        shares[model] = sum(counts[f] for f in sel) / TOTAL
        if reasons and model == "G3":
            why = sorted(reasons)[0]
    for p in writes:
        if classify(p) == "unmatched":
            unmatched[p.split("/", 1)[0] if "/" in p else p] += 1
    rows.append({"ts": ts[:10], "task": os.path.basename(src)[11:60], "files": len(writes), "tops": dict(tops),
                 **{k: round(v, 3) for k, v in shares.items()}, "full_reason": why})
json.dump(rows, open(f"/tmp/sel041/replay_{REPO}{'_code' if CODE_ONLY else ''}.json", "w"), indent=1)
print(f"{REPO}: {len(rows)} merged tasks, suite {TOTAL} tests in {len(counts)} files")
for r in rows:
    print(f"  {r['ts']} {r['task'][:44]:44} files={r['files']:>3} G1={r['G1']:.2f} G2={r['G2']:.2f} G3={r['G3']:.2f} "
          f"{r['full_reason'] or ''}  {r['tops']}")
for k in ("G1", "G2", "G3"):
    v = sorted(r[k] for r in rows)
    print(f"  {k}: median {v[len(v)//2]:.2f}, tasks selecting <50%: {sum(x < .5 for x in v)}, "
          f"<=10%: {sum(x <= .1 for x in v)}, ==0: {sum(x == 0 for x in v)}")
print("  unmatched top-levels:", dict(unmatched))
