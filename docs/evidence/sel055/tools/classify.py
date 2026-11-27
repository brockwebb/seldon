"""SEL-055 Part B: why each replayed plan went full: code (a path selection cannot vouch for under the evidence: the
package source, conftest, locks, the gate's configuration) or only non-code paths no slice names yet."""
import json
import sys
from pathlib import Path

REPO = sys.argv[1]
rows = json.loads(Path(f"/tmp/sel055/replay_{REPO}_new.json").read_text())
CODE_PREFIX = {"seldon": ("seldon/", "scripts/", "tests/", ".githooks/"),
               "hazbrief": ("src/", "scripts/", "tests/", "static/", "packs/", "fixtures/")}[REPO]
summary = {"scoped": 0, "full_code": 0, "full_noncode_only": 0}
for r in rows:
    if r.get("error"):
        continue
    if r["tier"] == "scoped":
        summary["scoped"] += 1
        kind = "scoped"
    else:
        code = [p for p in r["changed"] if p.startswith(CODE_PREFIX) or p.endswith("conftest.py")
                or p in ("pyproject.toml", "uv.lock", "seldon.yaml")]
        kind = "full_code" if code else "full_noncode_only"
        summary[kind] += 1
        r["code_paths"] = code
    noncode = [p for p in r["changed"] if p in r.get("unmatched", []) and p not in r.get("code_paths", [])]
    print(f"{r['task_id'][:8]}\t{kind}\tchanged={len(r['changed'])}\tcode={len(r.get('code_paths', []))}\t"
          f"unmatched_noncode={sorted(set(x.split('/')[0] + ('/' + x.split('/')[1] if x.count('/') > 1 else '') for x in noncode))[:6]}")
print(summary)
Path(f"/tmp/sel055/classified_{REPO}.json").write_text(json.dumps(rows, indent=1))
