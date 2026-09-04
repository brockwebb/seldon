"""``python -m seldon`` must work, because ``seldon verify --fix`` depends on it.

2026-09-04 defect sweep RESULT §7.5: the package had no ``__main__`` module, so
``python -m seldon`` failed with ``No module named seldon.__main__``.
``seldon/commands/verify.py`` shells out that way on purpose — ``sys.executable``
plus ``-m`` guarantees the child runs the same interpreter and the same checkout
as the parent, whereas the ``seldon`` console script resolves through whatever
install happens to be on PATH. Both ``--fix`` passes that use it
(``_fix_file_hashes``, ``_fix_ontology``) therefore raised ``CalledProcessError``
instead of syncing, and ``verify --fix`` degraded silently for anyone who had not
noticed the traceback.

These tests run the real subprocess rather than importing the module, because
importing ``seldon.__main__`` would not have caught the original defect: the
failure was that the module did not exist for ``runpy``, which is precisely what
``-m`` exercises.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from seldon.paths import distribution_root

#: The checkout under test. ``python -m`` puts the working directory first on
#: ``sys.path``, so running from here guarantees the subprocess imports THIS
#: ``seldon`` package and not an installed copy from site-packages.
REPO_ROOT = distribution_root()


def _run_module(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "seldon", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_main_module_file_exists():
    """The shim is a real file in the package, not a namespace accident."""
    assert (Path(REPO_ROOT) / "seldon" / "__main__.py").is_file()


def test_python_m_seldon_help_succeeds():
    """``python -m seldon --help`` exits 0 and prints the CLI banner."""
    result = _run_module("--help")
    assert result.returncode == 0, result.stderr
    assert "AI-assisted research artifact tracker" in result.stdout
    assert "No module named seldon.__main__" not in result.stderr


def test_python_m_seldon_exposes_the_same_commands_as_the_console_script():
    """The shim must not become a second, divergent CLI definition.

    ``seldon/cli.py`` is the single source of commands. If ``__main__`` ever
    grows its own group, ``python -m seldon`` and the ``seldon`` console script
    start disagreeing — the failure this shim exists to prevent.
    """
    from seldon.cli import main

    result = _run_module("--help")
    assert result.returncode == 0, result.stderr
    for command in main.commands:
        assert command in result.stdout, f"{command!r} missing from `python -m seldon --help`"


@pytest.mark.parametrize("subcommand", ["paper", "ontology"])
def test_verify_fix_subcommands_are_reachable_as_modules(subcommand):
    """The two groups ``verify --fix`` shells out to resolve under ``-m``.

    ``_fix_file_hashes`` runs ``-m seldon paper sync`` and ``_fix_ontology`` runs
    ``-m seldon ontology sync``. ``--help`` is used rather than ``sync`` so the
    test asserts reachability without touching a database.
    """
    result = _run_module(subcommand, "--help")
    assert result.returncode == 0, result.stderr
    assert "sync" in result.stdout
