"""Filesystem locations derived from where Seldon is installed.

Every default path in Seldon is derived here, from the location of the
``seldon`` package itself, or from an explicit environment override. Nothing in
this module may contain a user-specific absolute path.

Why this module exists (AD-adjacent, see cc_tasks/2026-09-03 defect sweep, D2):
defaults that named a developer's home directory kept working only because a
compatibility symlink happened to exist, and would have failed silently — with
a config file written to disk pointing at nothing — the moment it went away.
Deriving from the installed package location makes the default correct for a
source checkout, an editable install, and a wheel install, and makes "no
default could be found" a loud, diagnosable condition instead of a bad string.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import seldon

#: Environment variable that overrides the shared-ontology location.
ONTOLOGY_PATH_ENV = "SELDON_ONTOLOGY_PATH"

#: Environment variable that overrides the system engineering-standards file.
SYSTEM_STANDARDS_ENV = "SELDON_SYSTEM_CLAUDE_MD"

#: Directory name of the shared ontology tree, relative to its containing root.
ONTOLOGY_DIR_NAME = "ontology"

#: Vocabulary files, relative to the shared-ontology root, that a new project
#: inherits by default. Single source of truth: `seldon init` writes these into
#: `shared_ontology.vocabularies`, and the first entry doubles as the marker
#: that identifies a directory as an ontology root.
DEFAULT_VOCABULARIES = ("validity/VALIDITY_VOCABULARY.md",)

#: Path, relative to a candidate directory, that must exist for that directory
#: to BE a shared-ontology root.
#:
#: Existence of a directory named `ontology` is not sufficient evidence: the
#: `seldon` package itself contains a CODE package called `seldon/ontology/`
#: (the vocabulary parsers). Without this marker, deriving "package root +
#: 'ontology'" resolves to the parser package and every downstream vocabulary
#: read fails with a confusing error.
ONTOLOGY_MARKER = DEFAULT_VOCABULARIES[0]

#: Filename of the system-wide engineering standards document.
SYSTEM_STANDARDS_FILENAME = "CLAUDE.md"


def package_root() -> Path:
    """Return the directory containing the installed ``seldon`` package.

    Returns:
        Absolute, symlink-resolved path to the ``seldon/`` package directory.
    """
    return Path(seldon.__file__).resolve().parent


def distribution_root() -> Path:
    """Return the directory that contains the ``seldon`` package directory.

    For a source checkout or an editable install this is the repository root.
    For a wheel install it is ``site-packages``.

    Returns:
        Absolute, symlink-resolved path to the package's containing directory.
    """
    return package_root().parent


def ontology_source_candidates() -> list[Path]:
    """Return candidate shared-ontology root directories, in resolution order.

    The vocabulary tree is not packaged as package data, so it is found beside
    the package: at the repository root for a source checkout or an editable
    install. A wheel install has no such sibling, which is why
    :func:`resolve_ontology_source` can legitimately return None.

    Returns:
        Candidate directories, in resolution order. Neither existence nor
        validity is checked here.
    """
    return [distribution_root() / ONTOLOGY_DIR_NAME]


def is_ontology_root(path: Path) -> bool:
    """Return True if ``path`` is a shared-ontology root, not merely a directory.

    Args:
        path: Directory to test.

    Returns:
        True when the marker vocabulary file exists beneath ``path``.
    """
    return (path / ONTOLOGY_MARKER).is_file()


def resolve_ontology_source() -> Optional[Path]:
    """Resolve the shared-ontology root directory, or None if none exists.

    Resolution order:
      1. ``SELDON_ONTOLOGY_PATH``, which must name an existing directory. An
         explicit override is trusted as-is and is not marker-checked, so a
         project may point at a differently-shaped vocabulary tree.
      2. The first entry in :func:`ontology_source_candidates` that satisfies
         :func:`is_ontology_root`.

    Returns:
        Absolute path to the ontology root, or None when no candidate exists
        and no override is set. None is a real answer — the caller decides
        whether to degrade or to fail — but a *wrong* override is not.

    Raises:
        FileNotFoundError: If ``SELDON_ONTOLOGY_PATH`` is set but does not exist.
        NotADirectoryError: If ``SELDON_ONTOLOGY_PATH`` names an existing file
            rather than a directory. The shared-ontology *root* is a directory;
            ``seldon ontology`` separately accepts a single vocabulary *file*
            under the same variable name, so this is diagnosed explicitly rather
            than silently producing a ``<file>/<vocabulary>`` path that cannot
            exist.
    """
    override = os.getenv(ONTOLOGY_PATH_ENV)
    if override:
        path = Path(override).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"{ONTOLOGY_PATH_ENV} points to a non-existent path: {override}"
            )
        if not path.is_dir():
            raise NotADirectoryError(
                f"{ONTOLOGY_PATH_ENV} must name the shared-ontology root DIRECTORY "
                f"here, but names a file: {override}. "
                f"Point it at the directory that contains the vocabulary tree."
            )
        return path.resolve()

    for candidate in ontology_source_candidates():
        if candidate.is_dir() and is_ontology_root(candidate):
            return candidate
    return None


def system_standards_candidates() -> list[Path]:
    """Return candidate paths for the system-wide engineering standards file.

    The standards document governs every project under a common source root, so
    it lives one level above the repository that holds this package.

    Returns:
        Candidate file paths, in resolution order. Existence is not checked.
    """
    return [distribution_root().parent / SYSTEM_STANDARDS_FILENAME]


def resolve_system_standards() -> Optional[Path]:
    """Resolve the system engineering-standards file, or None if absent.

    Resolution order:
      1. ``SELDON_SYSTEM_CLAUDE_MD``, honoured only when the file exists.
      2. The first existing entry in :func:`system_standards_candidates`.

    Returns:
        Path to the standards file, or None when no candidate exists.
    """
    override = os.getenv(SYSTEM_STANDARDS_ENV)
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
    for candidate in system_standards_candidates():
        if candidate.is_file():
            return candidate
    return None


def resolve_ontology_root(
    configured_source: object, project_dir: Path
) -> Optional[Path]:
    """Resolve a project's ``shared_ontology.source`` to an ontology root.

    Two independent failures are covered here, and both are needed (2026-09-04
    defect sweep RESULT §7.6):

    * ``seldon.yaml`` may name the ontology tree by a *relative* path. Relative
      is the only form that is correct in every checkout of the same
      repository — an absolute path baked into committed config names one
      developer's clone, so a git worktree silently reads the *main* checkout's
      vocabulary and cannot test a vocabulary edit at all. Relative sources are
      joined to ``project_dir`` (the directory holding ``seldon.yaml``), not to
      the process CWD, so the answer does not depend on where the command was
      launched from.
    * The configured tree may be absent — a moved or renamed checkout, or a
      config with no ``shared_ontology.source`` at all. Rather than failing with
      "cannot locate vocabulary file", fall back to the tree that ships beside
      the installed package (:func:`ontology_source_candidates`).

    Neither half subsumes the other. The fallback alone does not fix the
    worktree case, because the hardcoded main-checkout path *exists* and so is
    never rejected; the relative rewrite alone does not help a project whose
    absolute source has moved.

    Args:
        configured_source: The raw ``shared_ontology.source`` value, or None.
        project_dir: Directory containing the project's ``seldon.yaml``.

    Returns:
        Absolute path to an existing ontology root directory, or None when
        neither the configured source nor any derived candidate exists.
    """
    if configured_source:
        candidate = Path(str(configured_source)).expanduser()
        if not candidate.is_absolute():
            candidate = Path(project_dir) / candidate
        if candidate.is_dir():
            return candidate.resolve()

    for candidate in ontology_source_candidates():
        if candidate.is_dir() and is_ontology_root(candidate):
            return candidate.resolve()
    return None
