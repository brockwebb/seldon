"""
Result units vocabulary loader (AD-028).

The vocabulary answers one question: is a given ``units`` string a REAL unit of
measurement, or a token key that was stashed in the wrong property?

Two consumers depend on that answer:

* ``seldon result migrate-names`` — a legacy Result whose ``units`` is a real
  unit keeps it; anything else is promoted to the ``name`` property.
* the transitional ``{{result:NAME:field}}`` units fallback in
  ``seldon/paper/build.py`` — it refuses to resolve a token against a Result
  whose ``units`` is a real unit, because that would be a coincidence, not a
  reference.

The list is data, not a Python literal, and it is packaged inside
``seldon.domain`` (covered by the existing ``"seldon.domain" = ["*.yaml"]``
package-data glob) so it survives a non-editable install. Nothing here resolves
paths relative to the current working directory or the repository root.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, Optional

import yaml

VOCABULARY_FILENAME = "result_units_vocabulary.yaml"

#: Keys in the YAML file whose list values are unioned into the vocabulary.
VOCABULARY_KEYS = ("seed_units", "codebase_units")


def vocabulary_path() -> Path:
    """Return the filesystem path of the packaged units vocabulary YAML.

    Resolved from this module's own location, never from the current working
    directory or a repository-root guess, so it works under a non-editable
    install where only the ``seldon`` package is present.

    Args:
        None.

    Returns:
        Absolute Path to ``seldon/domain/result_units_vocabulary.yaml``.

    Raises:
        Nothing. Existence is checked by :func:`load_units_vocabulary`.
    """
    return Path(__file__).resolve().parent / VOCABULARY_FILENAME


@lru_cache(maxsize=8)
def load_units_vocabulary(path: Optional[Path] = None) -> FrozenSet[str]:
    """Load the set of strings that count as real units of measurement.

    Args:
        path: Optional override for the YAML file. Defaults to the packaged
            vocabulary returned by :func:`vocabulary_path`. Tests use this to
            supply a fixture; production callers should pass nothing.

    Returns:
        Frozen set of unit strings, the union of every list named in
        :data:`VOCABULARY_KEYS`. Comparison is exact and case-sensitive.

    Raises:
        FileNotFoundError: If the vocabulary file is absent — which on a real
            install means the package-data glob stopped shipping it.
        ValueError: If the YAML does not parse to a mapping, contains none of
            the expected keys, holds a non-list under one of them, or holds a
            non-string / empty entry inside a list.
    """
    vocab_path = Path(path) if path is not None else vocabulary_path()
    if not vocab_path.exists():
        raise FileNotFoundError(
            f"Result units vocabulary not found at {vocab_path}. "
            f"It ships as package data under seldon/domain/ "
            f"(pyproject: [tool.setuptools.package-data] \"seldon.domain\" = [\"*.yaml\"]). "
            f"If this is an installed copy, the package data glob is broken."
        )

    with open(vocab_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Units vocabulary {vocab_path} must parse to a mapping, "
            f"got {type(raw).__name__}"
        )

    present = [key for key in VOCABULARY_KEYS if key in raw]
    if not present:
        raise ValueError(
            f"Units vocabulary {vocab_path} defines none of the expected keys "
            f"{list(VOCABULARY_KEYS)}"
        )

    units: set[str] = set()
    for key in present:
        entries = raw[key]
        if not isinstance(entries, list):
            raise ValueError(
                f"Units vocabulary {vocab_path}: '{key}' must be a list, "
                f"got {type(entries).__name__}"
            )
        for entry in entries:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError(
                    f"Units vocabulary {vocab_path}: '{key}' contains a "
                    f"non-string or empty entry {entry!r}"
                )
            units.add(entry)

    return frozenset(units)


def is_real_unit(units: Optional[str], vocabulary: Optional[FrozenSet[str]] = None) -> bool:
    """Report whether a ``units`` string is a real unit of measurement.

    Args:
        units: The Result's ``units`` property value. None or blank is not a
            unit.
        vocabulary: Optional pre-loaded vocabulary. Defaults to the packaged
            one.

    Returns:
        True if ``units`` appears verbatim in the vocabulary.

    Raises:
        FileNotFoundError: Propagated from :func:`load_units_vocabulary` when
            no vocabulary was supplied and the packaged file is missing.
        ValueError: Propagated from :func:`load_units_vocabulary` on a
            malformed vocabulary file.
    """
    if units is None:
        return False
    if vocabulary is None:
        vocabulary = load_units_vocabulary()
    return units in vocabulary
