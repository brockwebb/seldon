"""SEL-041 Part A: per-test-file collected counts, by `pytest --collect-only -q` in the repository's primary checkout.
Read only: -p no:cacheprovider writes no cache. Output: /tmp/sel041/collect_<repo>.json {file: count}."""
import json
import os
import subprocess
import sys

repo, python = sys.argv[1], sys.argv[2]
cwd = os.path.join("/Users/brock/GitHub", repo)
env = dict(os.environ)
if repo == "seldon":
    from dotenv import dotenv_values
    env.update({k: v for k, v in dotenv_values(os.path.join(cwd, ".env")).items() if v is not None})
out = subprocess.run([python, "-m", "pytest", "tests/", "--collect-only", "-q", "-p", "no:cacheprovider",
                      "-m", ""], cwd=cwd, env=env, capture_output=True, text=True)
counts = {}
for line in out.stdout.splitlines():
    if "::" in line:
        f = line.split("::", 1)[0]
        counts[f] = counts.get(f, 0) + 1
print(repo, "exit", out.returncode, "files", len(counts), "tests", sum(counts.values()))
print(out.stdout.splitlines()[-1:] , out.stderr[-500:])
json.dump(counts, open(f"/tmp/sel041/collect_{repo}.json", "w"), indent=0)
