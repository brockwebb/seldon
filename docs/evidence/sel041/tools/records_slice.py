"""SEL-041 Part D: the test files each of seldon's records slices requires: every test file that names a real
repository path under the slice's directories (tools/real_reads.py's literal scan, generic directory names excluded)
or joins the repository root with a path mentioning them (a grep of root joins), and their share of the suite by
collected count (/tmp/sel041/collect_seldon.json, Part A)."""
import json
import re
from pathlib import Path

WT = Path("/Users/brock/GitHub/seldon/.claude/worktrees/splendid-seeking-russell")
reads = json.load(open("/tmp/sel041/real_reads.json"))
counts = json.load(open("/tmp/sel041/collect_seldon.json"))
total = sum(counts.values())
GROUPS = {
    "documents": (("docs",), r"[\"'/]docs\b|decisions|register/|design/|conventions|evidence"),
    "task_records": (("cc_tasks", "handoffs"), r"cc_tasks|handoffs"),
    "ledgers": (("governed", "state"), r"governed|[\"'/]state/"),
    "graphs": (("graphs",), r"graphs/|seldon-biblio"),
}
root_join = re.compile(r"(SELDON_REPO|REPO_ROOT|\bREPO\b|\bROOT\b|parents\[1\]|\.parent\.parent)")
texts = {str(t.relative_to(WT)): t.read_text(encoding="utf-8") for t in (WT / "tests").glob("test_*.py")}
out = {}
for name, (tops, kw) in GROUPS.items():
    files = set()
    for top in tops:
        for f, lits in reads.get(top, {}).items():
            if any(l.rstrip("/") not in ("cc_tasks", "handoffs", "docs", "state", "graphs", "governed") for l in lits):
                files.add(f)
    rx = re.compile(kw)
    for f, txt in texts.items():
        if root_join.search(txt) and any(rx.search(line) and root_join.search(line) for line in txt.splitlines()):
            files.add(f)
    files = sorted(f for f in files if Path(f).name.startswith("test_") and "sel041" not in f)
    n = sum(counts.get(f, 0) for f in files)
    out[name] = files
    print(f"{name}: {len(files)} files, {n} of {total} tests ({n / total:.3f})")
json.dump(out, open("/tmp/sel041/records_slices.json", "w"), indent=1)
