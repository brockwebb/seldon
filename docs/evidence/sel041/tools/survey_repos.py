"""SEL-041 Part A: which repositories under ~/GitHub declare a dispatch block, their gate command, and gate logs."""
import glob
import os
import re
import sys

import yaml

ROOT = "/Users/brock/GitHub"
for d in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, d, "seldon.yaml")
    if not os.path.isfile(p):
        continue
    try:
        y = yaml.safe_load(open(p)) or {}
    except Exception as exc:  # report, never swallow
        print(d, "UNPARSEABLE", exc)
        continue
    disp = y.get("dispatch")
    if not isinstance(disp, dict):
        continue
    logdir = os.path.join(ROOT, d, disp.get("log_dir") or "logs/dispatch")
    gate_logs = glob.glob(os.path.join(logdir, "*.gate.log"))
    logs = glob.glob(os.path.join(logdir, "*.log"))
    print(f"== {d}: gate_command={disp.get('gate_command')!r} gate_record={disp.get('gate_record')!r} "
          f"max_parallel={disp.get('max_parallel')} slices={'gate' in disp}")
    print(f"   logdir={logdir} gate_logs={len(gate_logs)} logs={len(logs)}")
