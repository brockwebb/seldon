"""MODEL-003 Part C (ADDENDUM 01): probe one model once with no `--effort` and once per level, plus a control.

One unit per invocation, so no loop holds a result in memory (constitution 15): the unit is one CLI call; its key is
(model, effort, CLI version, prompt sha256); the checkpoint is `docs/evidence/model003/<slug>_effort_probes.jsonl`,
appended and fsynced when the call returns; re-running the same command skips a key already present (the resume
rule). The control level `bogus` is not a CLI level: if the CLI accepts it, acceptance says nothing about which levels
a model supports. Seven units in total, about $0.05 each (measured on the first manual probe: $0.038), under a
minute each; a unit that fails is a row with its error, not a crash.

    python scripts/model003/probe_effort.py claude-opus-4-8 none|low|medium|high|xhigh|max|bogus
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

from seldon import models as M  # noqa: E402

EVID = SELDON / "docs" / "evidence" / "model003"


def main(argv: list) -> int:
    if len(argv) != 2:
        raise SystemExit(__doc__)
    model, level = argv
    lock = M.load_lock()
    cfg = M.load_registry()["refresh"]
    prompt = cfg["probe_prompt"]
    key = {"model": model, "effort": level, "cli_version": str(lock["cli"]["version"]),
           "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    out = EVID / f"{model.replace('claude-', '').replace('-', '_')}_effort_probes.jsonl"
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip() and json.loads(line)["key"] == key:
                print(f"skip {level}: already in {out.name}")
                return 0
    cmd = M.probe_command(str(Path(lock["cli"]["path"]).expanduser()), model, prompt)
    if level != "none":
        cmd += ["--effort", level]
    started = datetime.now(timezone.utc)
    row = {"key": key, "argv": cmd, "started": started.isoformat()}
    try:
        res = subprocess.run(cmd, env=M.probe_env(), cwd=tempfile.mkdtemp(prefix="model003-"), capture_output=True,
                             text=True, timeout=int(cfg["probe_timeout_s"]))
        env = M.last_result_envelope(res.stdout) or {}
        mu = env.get("modelUsage") or {}
        served = M.served_model(env)
        row.update({"exit_code": res.returncode, "served": served, "accepted": res.returncode == 0 and served == model,
                    "is_error": env.get("is_error"), "result": env.get("result"),
                    "output_tokens": (mu.get(served) or {}).get("outputTokens"),
                    "thinking_tokens": (mu.get(served) or {}).get("thinkingTokens"),
                    "cost_usd": env.get("total_cost_usd"), "stderr_tail": (res.stderr or "")[-400:]})
    except (subprocess.SubprocessError, OSError) as exc:
        row.update({"exit_code": None, "accepted": False, "error": f"{type(exc).__name__}: {exc}"})
    row["seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 2)
    EVID.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(f"{level}: exit {row['exit_code']} served {row.get('served')} accepted {row['accepted']} "
          f"thinking {row.get('thinking_tokens')} ${row.get('cost_usd')} {row['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
