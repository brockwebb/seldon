"""SEC-001R: replace inline secrets in claude_desktop_config.json with scripts/mcp_launch.sh.

For every server in servers.yaml whose config `env` block carries a secret-shaped key, the
server is rewritten to

    command: <launcher>
    args:    [<dir>, --only, <KEYS>, --, <old command>, <old args>...]
    env:     <old env minus the secret keys>

but ONLY if <dir>/.env already holds every one of those keys with the identical value
(parsed by python-dotenv, the parser mcp_launch.sh is tested to match). A server whose
.env lacks a key is reported and left untouched, so a rewrite can never start a server
without its credential. This script never writes, prints or copies a secret value: moving
a value into a .env is the operator's act.

Usage:
    python scripts/sec001/rewrite_desktop_config.py                  # dry run: report only
    python scripts/sec001/rewrite_desktop_config.py --evidence DIR   # also write redacted evidence
    python scripts/sec001/rewrite_desktop_config.py --apply          # rewrite the config in place

Exit 0 when nothing secret is left inline (after --apply, or would be, on a dry run),
1 when some server still carries an inline secret, 2 on a refusal.
"""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

import yaml
from dotenv import dotenv_values

HERE = Path(__file__).parent
REDACTED = "<redacted>"


def plan(cfg: dict, spec: dict) -> tuple[dict, list[str], list[str]]:
    """Return (rewritten config, report lines, servers still holding inline secrets).

    Raises:
        SystemExit: a .env holds a moved key with a DIFFERENT value (refuse, exit 2).
    """
    secret = re.compile(spec["secret_key_pattern"])
    out = json.loads(json.dumps(cfg))
    report, inline = [], []
    for name, server in out["mcpServers"].items():
        secrets = sorted(k for k in server.get("env", {}) if secret.search(k))
        if not secrets:
            continue
        directory = spec["servers"].get(name)
        if directory is None:
            report.append(f"{name}: {secrets} LEFT INLINE: no directory mapped in servers.yaml")
            inline.append(name)
            continue
        envfile = Path(directory) / ".env"
        have = dotenv_values(envfile, interpolate=False) if envfile.is_file() else {}
        missing = [k for k in secrets if k not in have]
        if missing:
            report.append(f"{name}: {secrets} LEFT INLINE: {envfile} lacks {missing}")
            inline.append(name)
            continue
        differ = [k for k in secrets if have[k] != server["env"][k]]
        if differ:
            sys.exit(f"refused: {envfile} holds {differ} with a value different from server "
                     f"{name}'s; reconcile by hand")
        server["args"] = [directory, "--only", ",".join(secrets), "--",
                          server["command"], *server.get("args", [])]
        server["command"] = spec["launcher"]
        server["env"] = {k: v for k, v in server["env"].items() if k not in secrets}
        report.append(f"{name}: {secrets} -> reads {envfile}")
    return out, report, inline


def redact(cfg: dict, pattern: str) -> dict:
    """Copy of cfg with every secret-shaped env value replaced by REDACTED."""
    secret = re.compile(pattern)
    out = json.loads(json.dumps(cfg))
    for server in out["mcpServers"].values():
        for k in server.get("env", {}):
            if secret.search(k):
                server["env"][k] = REDACTED
    return out


def write_atomic(path: Path, text: str) -> None:
    """Replace path with text via a same-directory temp file, fsynced, mode 600."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.sec001r-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--spec", default=str(HERE / "servers.yaml"))
    ap.add_argument("--apply", action="store_true", help="rewrite the config in place")
    ap.add_argument("--evidence", help="directory for the redacted config and per-server lines")
    args = ap.parse_args()

    spec = yaml.safe_load(Path(args.spec).read_text())
    cfg_path = Path(spec["config"])
    raw = cfg_path.read_text()
    cfg = json.loads(raw)
    tail = "\n" if raw.endswith("\n") else ""
    # The rewrite re-serialises the whole file; refuse if that would change anything but
    # the servers it means to change.
    if json.dumps(cfg, indent=2, ensure_ascii=False) + tail != raw:
        sys.exit("refused: the config does not round-trip byte-identically through json")

    new, report, inline = plan(cfg, spec)
    print("\n".join(report))
    if args.evidence:
        ev = Path(args.evidence)
        ev.mkdir(parents=True, exist_ok=True)
        (ev / "config_after.json").write_text(
            json.dumps(redact(new, spec["secret_key_pattern"]), indent=2, ensure_ascii=False) + "\n")
        (ev / "servers.txt").write_text("\n".join(report) + "\n")
    if args.apply:
        write_atomic(cfg_path, json.dumps(new, indent=2, ensure_ascii=False) + tail)
        print(f"rewrote {cfg_path}")
    else:
        print("dry run: config not written")
    return 1 if inline else 0


if __name__ == "__main__":
    sys.exit(main())
