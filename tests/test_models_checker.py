"""QC-001 Part D (AD-037-R2): the `checker` role is the next tier above the generator, resolved through the lock.

haiku -> sonnet, sonnet -> opus, opus -> fable, and fable -> fable with authorship obfuscation (S2, a partial fix:
nothing sits above Fable). `seldon.models.resolve("checker", generator=<role>)` returns the locked id.
"""
from __future__ import annotations

import pytest

from seldon import models as M
from tests.models_fixture import FIXTURE_IDS, write_models_home


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = write_models_home(tmp_path)
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(h))
    return h


#: One registry role per generator family, and the family its checker must be.
CASES = [("background", "haiku", "sonnet", False), ("extractor", "sonnet", "opus", False),
         ("primary", "opus", "fable", False), ("judge", "fable", "fable", True)]


@pytest.mark.parametrize("generator,gen_family,checker_family,obfuscate", CASES)
def test_the_checker_is_the_next_tier_for_every_family(home, generator, gen_family, checker_family, obfuscate):
    assert M.resolve_role(generator).family == gen_family, "the case table no longer matches the registry"
    assert M.resolve("checker", generator=generator) == FIXTURE_IDS[checker_family]
    res = M.resolve_role("checker", generator=generator)
    assert res.family == checker_family and res.obfuscate is obfuscate


def test_a_checker_without_a_generator_or_with_an_unknown_one_is_refused(home):
    with pytest.raises(M.ModelsError, match="generator"):
        M.resolve("checker")
    with pytest.raises(M.UnknownRole):
        M.resolve("checker", generator="no_such_role")
    with pytest.raises(M.ModelsError, match="generator"):
        M.resolve("primary", generator="extractor")
