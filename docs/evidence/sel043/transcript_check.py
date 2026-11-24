"""SEL-043 erratum check for tests/fixtures/dispatch_serial_transcript.txt: the re-recording equals the pre-change
fixture once SEL-043's additions are removed. Prints True or the first differing lines.

Removed from the re-recording, and nothing else:
- in each `premises.environment` (station (a)'s premise, AD-037-R17, R18): the keys `not_holding` and `pins`, and the
  statement's new wording put back to the old;
- in each `gate_run` record (AD-037-R21): `started_at`, `ended_at`, `wall_seconds`, `asleep_s`.
UUID and HEX placeholders are renumbered by first appearance in both, since removed timestamps shift nothing but
removed values may.

Usage: python docs/evidence/sel043/transcript_check.py <before.txt> <after.txt>
"""
import json
import re
import sys

OLD_STATEMENT = "no other project's dispatcher holds a lease on a repository this task's environment names"
WALL_KEYS = ("started_at", "ended_at", "wall_seconds", "asleep_s")


#: A placeholder `normalize` writes in a value position (`"free_bytes": <HEX-12>`), which is not JSON.
_VALUE_TOKEN = re.compile(r"(?<=[:\[,] )<([A-Z]+(?:-\d+)?)>|(?<=\[)<([A-Z]+(?:-\d+)?)>")


def load(line: str):
    t = _VALUE_TOKEN.sub(lambda m: f'"__tok:{m.group(1) or m.group(2)}__"', line)
    return json.loads(t)


def dump(ev) -> str:
    t = json.dumps(ev, sort_keys=True)
    return re.sub(r'"__tok:([A-Z]+(?:-\d+)?)__"', r"<\1>", t)


def strip_event(ev):
    if ev.get("event_type") == "gate_run":
        for k in WALL_KEYS:
            ev["payload"].pop(k, None)

    def walk(d):
        if isinstance(d, dict):
            env = d.get("environment")
            if isinstance(env, dict) and env.get("source") == "dispatcher":
                env.pop("not_holding", None)
                env.pop("pins", None)
                env["statement"] = OLD_STATEMENT
            for v in d.values():
                walk(v)
        elif isinstance(d, list):
            for v in d:
                walk(v)
    walk(ev)
    return ev


def canon(text: str, strip: bool) -> str:
    out = []
    for line in text.splitlines():
        if line.startswith("{"):
            ev = load(line)   # every event line must parse: one that did not would pass through unstripped
            line = dump(strip_event(ev) if strip else ev)
        out.append(line)
    text = "\n".join(out)
    seen = {}
    return re.sub(r"<(UUID|HEX)-\d+>", lambda m: seen.setdefault(m.group(0), f"<{m.group(1)[0]}{len(seen)}>"), text)


before = canon(open(sys.argv[1], encoding="utf-8").read(), strip=False)
after = canon(open(sys.argv[2], encoding="utf-8").read(), strip=True)
if before == after:
    print(True)
else:
    for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines())):
        if a != b:
            print("line", i + 1)
            print("before:", a[:1500])
            print("after: ", b[:1500])
            break
    print(False)
