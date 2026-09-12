"""Verify that the Squiddy the build will use is the Squiddy this graph is pinned to (AD-030-R17).

Every build target in this graph's Makefile depends on this check. A graph built against an
unpinned kit is not reproducible, and discovering that after the ledger has been appended to is
discovering it too late: the ledger is append-only, so an admission made by the wrong parser stays
in the record.

The check is deliberately loud and specific. It names the pinned commit, the commit actually
checked out, the path it looked in, and the one command that fixes it — because the failure it
guards against is a developer who has two checkouts and no reason to suspect which one is on
`sys.path`.

    python governed/check_pin.py --graph governed
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

#: Name of the pin file, relative to the graph root.
PIN_FILENAME = "squiddy.pin"


def read_pin(graph_root: Path) -> dict[str, str]:
    """Read `squiddy.pin` into a mapping.

    Args:
        graph_root: The graph directory.

    Returns:
        `{"SQUIDDY_COMMIT": ..., "SQUIDDY_VERSION": ...}`.

    Raises:
        SystemExit: If the file is absent or names no commit. An absent pin is not "unpinned by
            default"; it is a build whose reproducibility nobody has stated.
    """
    path = graph_root / PIN_FILENAME
    if not path.is_file():
        raise SystemExit(
            f"FATAL: no {PIN_FILENAME} at {path}. This graph pins its kit by commit (AD-030-R17); "
            f"a build with no pin is not reproducible."
        )
    pin: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        pin[key.strip()] = value.strip()
    if not pin.get("SQUIDDY_COMMIT"):
        raise SystemExit(f"FATAL: {path} declares no SQUIDDY_COMMIT.")
    return pin


def installed_squiddy() -> Path:
    """Where the Squiddy that `import squiddy` resolves to actually lives.

    Returns:
        The package directory.

    Raises:
        SystemExit: If Squiddy is not importable.
    """
    try:
        import squiddy
    except ImportError:
        raise SystemExit(
            "FATAL: squiddy is not importable. This graph is built with the Squiddy kit "
            "(AD-030-R17); install it, or run make with PY=<interpreter that has it>."
        )
    return Path(squiddy.__file__).resolve().parent


def head_commit(repo: Path) -> str | None:
    """Return the commit checked out at `repo`, or None when it is not a git work tree.

    Args:
        repo: A directory inside the repository.

    Returns:
        The full commit hash, or None.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--graph", required=True, help="the graph directory (holds squiddy.pin)")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args(argv)

    graph_root = Path(args.graph).resolve()
    pin = read_pin(graph_root)
    wanted = pin["SQUIDDY_COMMIT"]

    package = installed_squiddy()
    checkout = package.parent
    actual = head_commit(checkout)

    if actual is None:
        print(
            f"FATAL: squiddy resolves to {package}, which is not a git work tree, so the pinned "
            f"commit cannot be verified.\n"
            f"  Pinned: {wanted}\n"
            f"  Fix: install squiddy from a checkout (`pip install -e /path/to/squiddy`), or move "
            f"the pin to a form this graph can check.",
            file=sys.stderr,
        )
        return 1

    if actual != wanted:
        print(
            f"FATAL: the checked-out Squiddy is not the one this graph is pinned to.\n"
            f"  Pinned:  {wanted}  ({PIN_FILENAME})\n"
            f"  Present: {actual}  ({checkout})\n"
            f"  Why this matters: the extraction is a function of the parser, the assess criterion\n"
            f"  and the acquire adapter at a specific commit, and the ledger is append-only — an\n"
            f"  admission made by the wrong parser stays in the record.\n"
            f"  Fix: `git -C {checkout} checkout {wanted}`, or move the pin deliberately and\n"
            f"  re-run `make -C {graph_root.name} kit-schema schema` and the sweep.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"squiddy pin ok: {wanted[:12]} at {checkout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
