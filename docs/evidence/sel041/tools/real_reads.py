"""SEL-041 Part D: which test files name a real repository path under each non-code top-level directory (a string
literal that is an existing file or directory of the checkout), so seldon's `tests: none` slices are declared only
where no test reads the real files, and the others name the tests that do."""
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1])
TOPS = ["docs", "cc_tasks", "handoffs", "governed", "state", "graphs", "scripts", "ontology", "paper", "seldon.yaml",
        ".githooks", "templates", "README.md", "CLAUDE.md"]
out = defaultdict(lambda: defaultdict(set))
for t in sorted((ROOT / "tests").glob("**/*.py")):
    try:
        tree = ast.parse(t.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for c in consts:
        c = c.strip().lstrip("./")
        top = c.split("/", 1)[0]
        if top in TOPS and len(c) < 300 and (ROOT / c).exists():
            # a bare top-level name ("docs") is usually a tmp fixture's directory; only count deeper real paths,
            # or the files themselves (seldon.yaml, README.md)
            if "/" in c or top in ("seldon.yaml", "README.md", "CLAUDE.md"):
                out[top][str(t.relative_to(ROOT))].add(c)
res = {top: {f: sorted(v)[:5] for f, v in files.items()} for top, files in out.items()}
json.dump(res, open("/tmp/sel041/real_reads.json", "w"), indent=1)
for top, files in sorted(res.items()):
    print(f"{top}: {len(files)} test file(s): {', '.join(sorted(files)[:12])}")
