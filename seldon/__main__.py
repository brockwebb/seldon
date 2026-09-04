"""Module entry point so ``python -m seldon`` runs the Seldon CLI.

Why this file exists (2026-09-04 defect sweep RESULT §7.5): the ``seldon``
console script is the *installed* entry point, which resolves through whatever
``site-packages``/editable install is active — not necessarily the checkout the
caller is standing in. ``seldon/commands/verify.py`` therefore shells out with
``[sys.executable, "-m", "seldon", ...]`` for its ``--fix`` passes, so that the
child process runs the same interpreter and the same code as the parent.

Without a ``__main__`` module that invocation failed with
``No module named seldon.__main__``, and ``verify --fix`` silently degraded:
``_fix_file_hashes`` and ``_fix_ontology`` both raised
``CalledProcessError`` instead of syncing.

Keep this file a thin shim. Everything that is a command belongs in
``seldon/cli.py``; duplicating argument handling here would make ``python -m
seldon`` and ``seldon`` diverge, which is the failure this shim exists to
prevent.
"""

from __future__ import annotations

from seldon.cli import main

if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    main()
