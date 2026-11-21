"""SEL-041 erratum check for tests/fixtures/dispatch_serial_transcript.txt: the re-recording equals the pre-change
fixture once the `gate_run` event line and the four new gate keys (`tier`, `reason`, `seconds`, `gate_run`) are removed
and UUID placeholders are renumbered by first appearance. Prints True or the first differing lines.

Usage: python docs/evidence/sel041/transcript_check.py <before.txt> <after.txt>
"""
import json
import re
import sys

NEW_KEYS = ("tier", "reason", "seconds", "gate_run")


def strip(text: str) -> str:
    out = []
    for line in text.splitlines():
        if '"event_type": "gate_run"' in line:
            continue
        # The journal commit that carries the record names its event type and counts its line.
        m = re.search(r", gate_run (<HEX-\d+>) — (\d+) line\(s\)", line)
        if m:
            line = line.replace(m.group(0), f" {m.group(1)} — {int(m.group(2)) - 1} line(s)")
        if line.startswith("{") and '"gate"' in line:
            ev = json.loads(line.replace("<WALL>", "0").replace("<SECONDS>", "0"))

            def drop(d):
                if isinstance(d, dict):
                    if {"exit_code", "log_path", "ok"} <= set(d):
                        for k in NEW_KEYS:
                            d.pop(k, None)
                    for v in d.values():
                        drop(v)
            drop(ev)
            line = json.dumps(ev, sort_keys=True).replace('"wall_clock_s": 0', '"wall_clock_s": <WALL>')
        out.append(line)
    text = "\n".join(out)
    seen = {}
    return re.sub(r"<(UUID|HEX)-\d+>", lambda m: seen.setdefault(m.group(0), f"<{m.group(1)[0]}{len(seen)}>"), text)


def canon(text: str) -> str:
    """Event lines re-serialised with sorted keys, so key order does not count as a difference."""
    lines = []
    for line in text.splitlines():
        if line.startswith("{"):
            try:
                line = json.dumps(json.loads(line.replace("<WALL>", "0")), sort_keys=True).replace(
                    '"wall_clock_s": 0', '"wall_clock_s": <WALL>')
            except json.JSONDecodeError:
                pass
        lines.append(line)
    return "\n".join(lines)


before = canon(open(sys.argv[1], encoding="utf-8").read())
after = strip(canon(open(sys.argv[2], encoding="utf-8").read()))
seen = {}
before = re.sub(r"<(UUID|HEX)-\d+>", lambda m: seen.setdefault(m.group(0), f"<{m.group(1)[0]}{len(seen)}>"), before)
if before == after:
    print(True)
else:
    for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines())):
        if a != b:
            print("line", i, "\n before:", a[:400], "\n after: ", b[:400])
            break
    print(False, len(before.splitlines()), len(after.splitlines()))
