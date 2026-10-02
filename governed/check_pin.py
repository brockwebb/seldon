"""Verify that the Squiddy the build will use is the Squiddy this graph is pinned to (AD-030-R17).

Every build target in this graph's Makefile depends on this check. A graph built against an
unpinned kit is not reproducible, and discovering that after the ledger has been appended to is
discovering it too late: the ledger is append-only, so an admission made by the wrong parser stays
in the record.

The check is deliberately loud and specific. It names the pinned commit, the commit actually
checked out, the path it looked in, and the one command that fixes it — because the failure it
guards against is a developer who has two checkouts and no reason to suspect which one is on
`sys.path`.

What it binds is the kit's `squiddy/` package tree, not the kit repository's HEAD (SEL-001,
`kit_matches`): a later commit that leaves that tree byte-identical passes, so a docs commit to the
kit, or the commit that adds a governed graph to the kit's own repository, does not break the pin.

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


#: The kit's package directory inside its checkout. The pin binds THIS tree: the parser, the assess
#: criterion and the acquire adapter are in it, and nothing outside it runs when this graph is built.
KIT_PACKAGE = "squiddy"


def _git_out(repo: Path, *args: str) -> str | None:
    """`git -C repo <args>` stdout, or None when git refuses."""
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def kit_matches(checkout: Path, wanted: str) -> tuple[bool, str]:
    """Whether the kit checked out at `checkout` is the kit this graph is pinned to (SEL-001).

    THE PIN BINDS THE KIT'S CODE, NOT THE KIT REPOSITORY'S HEAD. Equal HEADs pass. A later HEAD passes
    when its `squiddy/` package tree is the pinned commit's tree, byte for byte (git's tree hash), so a
    commit that touches only the kit's docs, tests or graphs, and the commit that adds a governed graph
    to the kit's own repository, leave the pin holding. Either way the package must have no uncommitted
    change: a dirty tree is a parser no commit names.

    Args:
        checkout: The kit's git work tree.
        wanted: The pinned commit.

    Returns:
        `(ok, how)`: how names what matched, or what did not.
    """
    head = _git_out(checkout, "rev-parse", "HEAD")
    if head is None:
        return False, f"{checkout} is not a git work tree"
    dirty = _git_out(checkout, "status", "--porcelain", "--", KIT_PACKAGE)
    if dirty:
        return False, (f"{KIT_PACKAGE}/ has uncommitted changes at {checkout}:\n    "
                       + "\n    ".join(dirty.splitlines()[:5]))
    if head == wanted:
        return True, f"HEAD is the pinned commit {wanted[:12]}"
    pinned_tree = _git_out(checkout, "rev-parse", f"{wanted}:{KIT_PACKAGE}")
    head_tree = _git_out(checkout, "rev-parse", f"HEAD:{KIT_PACKAGE}")
    if pinned_tree is None:
        return False, f"the pinned commit {wanted[:12]} is not in {checkout}, or has no {KIT_PACKAGE}/ tree"
    if pinned_tree == head_tree:
        return True, (f"HEAD {head[:12]} carries the pinned commit's {KIT_PACKAGE}/ tree "
                      f"{pinned_tree[:12]} unchanged")
    return False, (f"{KIT_PACKAGE}/ at HEAD {head[:12]} (tree {str(head_tree)[:12]}) is not the pinned "
                   f"commit's (tree {pinned_tree[:12]})")


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
    ok, how = kit_matches(checkout, wanted)
    if not ok:
        print(
            f"FATAL: the checked-out Squiddy is not the one this graph is pinned to.\n"
            f"  Pinned:  {wanted}  ({PIN_FILENAME})\n"
            f"  Present: {how}  ({checkout})\n"
            f"  Why this matters: the extraction is a function of the parser, the assess criterion\n"
            f"  and the acquire adapter at a specific commit, and the ledger is append-only — an\n"
            f"  admission made by the wrong parser stays in the record.\n"
            f"  Fix: `git -C {checkout} checkout {wanted}`, or move the pin deliberately and\n"
            f"  re-run `make -C {graph_root.name} kit-schema schema` and the sweep.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"squiddy pin ok: {how} ({checkout})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
