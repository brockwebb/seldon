"""SEL-063 Part B: configuration that names one machine, and the adopters (REVIEW-001 F-28 to F-33).

- F-28: `prior_art.internal_roots_from` raised when no sibling factory checkout exists, on the commit hook, `verify`
  and `cc register` paths. A missing portfolio file is now a reported, degraded search (AD-036-R32 amended).
- F-29: `dispatch.hive.mint_command` named one machine's interpreter and checkout.
- F-30: `scripts/sel056/*.sh` `rm -rf` an unchecked argument and hardcode one machine's squiddy.
- F-31: the shipped `gate_command` needs pytest-xdist and relies on pytest-randomly; neither was declared, and the
  README had no install section.
- F-32: `hooks.status` reads this checkout's own `config.worktree`; the shared value is advisory (AD-036-R31 amended).
- F-33: the pa002 rebuild test skipped through `importorskip("squiddy.index")`, so a gate without squiddy passed it
  unrun.

Names that do not exist at the branch's base are reached inside the tests, so Part A's check (which collects this
module) is not broken by them. Each test fails at the base (`1c8d372`).
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from seldon.core import hooks as H
from seldon.core import prior_art as pa

KIT = Path(__file__).resolve().parents[1]
SCRIPTS = KIT / "scripts" / "sel056"


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True, env=env)


def _repo(path: Path, files: dict) -> Path:
    path.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["config", "core.hooksPath", "/dev/null"]):
        _git(path, *args)
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


# ------------------------------------------------------------------------------------------------ F-28

def _pa_config(ws: Path, roots_from: str | None) -> dict:
    block = {
        "log": "state/q.jsonl",
        "internal_roots": [{"name": "kit", "path": "."}],
        "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"], "top_n": 20,
                     "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
        "library": {"graph": str(ws / "nolib"), "k": 20},
        "gate": {"design_dir": "docs/design", "baseline": "docs/design/base.txt", "exempt_globs": [],
                 "verdict_ledger_without_governed": "state/v.jsonl"},
    }
    if roots_from is not None:
        block[pa.ROOTS_FROM_KEY] = roots_from
    return {"project": {"name": "kit"}, "prior_art": block}


def test_part_b_a_missing_portfolio_file_is_a_noted_degraded_search_not_a_settings_error(tmp_path):
    kit = _repo(tmp_path / "kit", {"docs/design/AD-001.md": "# kit\n\nThe oscillator drift.\n"})
    s = pa.settings(kit, _pa_config(tmp_path, "../factory/seldon.yaml#portfolio.repositories"))
    assert [r.name for r in s.roots] == ["kit"]
    assert len(s.notes) == 1
    assert "../factory/seldon.yaml" in s.notes[0] and "does not exist" in s.notes[0]
    assert "internal_roots only" in s.notes[0]


def test_part_b_a_degraded_search_says_so_in_its_output(tmp_path):
    from seldon.commands import prior_art as PC

    cfg = _pa_config(tmp_path, "../factory/seldon.yaml#portfolio.repositories")
    kit = _repo(tmp_path / "kit", {"docs/design/AD-001.md": "# kit\n\nThe oscillator drift.\n",
                                   "seldon.yaml": yaml.safe_dump(cfg), ".gitignore": "state/v.jsonl\n"})
    out = PC.run_search("internal", "oscillator drift", project_dir=kit, config=cfg)
    assert [h["root"] for h in out["top"]] == ["kit"]
    assert any("does not exist" in n for n in out["notes"])


def test_part_b_a_malformed_portfolio_reference_is_still_refused(tmp_path):
    kit = _repo(tmp_path / "kit", {"docs/design/AD-001.md": "# kit\n"})
    (tmp_path / "factory").mkdir()
    (tmp_path / "factory" / "seldon.yaml").write_text(yaml.safe_dump({"portfolio": {"other": {}}}))
    for ref, needle in (("no-hash", "not a reference"), ("../factory/seldon.yaml#portfolio.repositories", "has no")):
        with pytest.raises(pa.PriorArtError, match=needle):
            pa.settings(kit, _pa_config(tmp_path, ref))


# ------------------------------------------------------------------------------------------------ F-29

def test_part_b_a_hive_command_resolves_the_interpreter_and_kit_relative_paths(tmp_path):
    from seldon.core import hive as HV

    hive = HV.load_hive({"mint_command": "{python} ../factory/scripts/hive.py mint",
                         "notices_hook": "{python} ../factory/scripts/hive.py notices --hook"}, base=tmp_path / "kit")
    script = str((tmp_path / "factory" / "scripts" / "hive.py").resolve())
    assert shlex.split(hive["mint_command"]) == [sys.executable, script, "mint"]
    assert shlex.split(hive["notices_hook"]) == [sys.executable, script, "notices", "--hook"]


def test_part_b_seldons_hive_block_names_no_machines_paths():
    from seldon.core import dispatch as D
    from seldon.core import worktree as WT

    raw = yaml.safe_load((KIT / "seldon.yaml").read_text(encoding="utf-8"))["dispatch"]["hive"]
    for key in ("mint_command", "notices_hook"):
        words = shlex.split(raw[key])
        assert not any(w.startswith("/") for w in words), (key, raw[key])
    cfg = D.load_dispatch_config(KIT)
    script = str((WT.anchor(KIT) / ".." / "factory" / "scripts" / "hive.py").resolve())
    assert shlex.split(cfg["hive"]["mint_command"])[:2] == [sys.executable, script]


# ------------------------------------------------------------------------------------------------ F-30

def _bash(script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPTS / script), *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})}, timeout=120)


def test_part_b_no_sel056_script_names_one_machines_path():
    for f in sorted(SCRIPTS.glob("*.sh")):
        text = f.read_text(encoding="utf-8")
        assert "/Users/" not in text and "/opt/" not in text, f.name


def test_part_b_trial_refuses_a_scratch_directory_it_did_not_make(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("not the script's\n")
    out = _bash("trial.sh", str(victim))
    assert out.returncode != 0
    assert (victim / "keep.txt").is_file()
    assert "was not made by" in out.stderr


def test_part_b_a_scratch_directory_outside_the_temporary_directories_is_refused(tmp_path):
    lib = SCRIPTS / "lib.sh"
    out = subprocess.run(["bash", "-c", f'source "{lib}" && sel056_fresh_scratch "$1"', "_", str(KIT / "docs")],
                         capture_output=True, text=True)
    assert out.returncode != 0
    assert "not under" in out.stderr
    assert (KIT / "docs").is_dir()


def test_part_b_a_scratch_directory_is_made_marked_and_remade(tmp_path):
    lib = SCRIPTS / "lib.sh"
    scratch = tmp_path / "s"

    def fresh() -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", f'source "{lib}" && sel056_fresh_scratch "$1"', "_", str(scratch)],
                              capture_output=True, text=True)

    assert fresh().returncode == 0
    marker = scratch / ".sel056_scratch"
    assert marker.is_file()
    (scratch / "left.txt").write_text("from the last run\n")
    assert fresh().returncode == 0
    assert marker.is_file() and not (scratch / "left.txt").exists()


def test_part_b_the_squiddy_wrapper_finds_the_kit_beside_the_primary_checkout(tmp_path):
    lib = SCRIPTS / "lib.sh"
    out = subprocess.run(["bash", "-c", f'source "{lib}" && sel056_squiddy_root'], capture_output=True, text=True,
                         cwd=KIT)
    from seldon.core import worktree as WT
    assert out.returncode == 0, out.stderr
    assert Path(out.stdout.strip()) == (WT.anchor(KIT) / ".." / "squiddy").resolve()
    over = subprocess.run(["bash", "-c", f'source "{lib}" && sel056_squiddy_root'], capture_output=True, text=True,
                          cwd=KIT, env={**os.environ, "SQUIDDY_ROOT": str(tmp_path)})
    assert Path(over.stdout.strip()) == tmp_path


# ------------------------------------------------------------------------------------------------ F-31

def test_part_b_the_gate_commands_plugins_are_declared_in_the_dev_extras():
    dev = tomllib.loads((KIT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]["dev"]
    names = {d.split(">")[0].split("=")[0].split("<")[0].strip().lower() for d in dev}
    gate = shlex.split(yaml.safe_load((KIT / "seldon.yaml").read_text(encoding="utf-8"))["dispatch"]["gate_command"])
    if "-n" in gate:
        assert "pytest-xdist" in names
    # The gate_command's comment relies on pytest-randomly reordering every run.
    assert "pytest-randomly" in names
    assert "python-dotenv" in {d.split(">")[0].strip().lower() for d in tomllib.loads(
        (KIT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]}


def test_part_b_the_readme_has_an_install_section_with_one_working_command():
    text = (KIT / "README.md").read_text(encoding="utf-8")
    assert "\n## Install\n" in text
    section = text.split("\n## Install\n", 1)[1].split("\n## ", 1)[0]
    assert 'pip install -e ".[dev]"' in section
    assert "python -m dotenv -f .env run -- python -m pytest tests/" in section


# ------------------------------------------------------------------------------------------------ F-32

@pytest.fixture
def installed(tmp_path):
    p = tmp_path / "primary"
    p.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(p, *args)
    (p / "README.md").write_text("x\n", encoding="utf-8")
    _git(p, "add", "README.md")
    _git(p, "commit", "-q", "-m", "init")
    H.install(p, python=sys.executable, commit=False)
    _git(p, "add", "-A")
    _git(p, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "hooks")
    return p


def test_part_b_whatever_the_shared_value_a_pointed_checkout_reads_installed(installed):
    _git(installed, "config", "--local", "core.hooksPath", "/somewhere/a/later/cli/wrote")
    st = H.status(installed)
    assert st["installed"], st["problems"]
    assert st["advisories"] and "/somewhere/a/later/cli/wrote" in st["advisories"][0]
    assert st["scope"] == "worktree"


def test_part_b_the_installed_shared_value_gives_no_advisory(installed):
    st = H.status(installed)
    assert st["installed"] and st["advisories"] == []


def test_part_b_a_checkout_nobody_pointed_is_not_installed(installed):
    _git(installed, "config", "--worktree", "--unset", "core.hooksPath")
    st = H.status(installed)
    assert not st["installed"]
    assert any("config.worktree" in p for p in st["problems"]), st["problems"]


# ------------------------------------------------------------------------------------------------ F-33

def test_part_b_the_pa002_rebuild_test_fails_rather_than_skips_without_squiddy(monkeypatch):
    from tests import squiddy_premise as SP

    monkeypatch.setitem(sys.modules, "squiddy.index", None)        # `import squiddy.index` raises ImportError
    monkeypatch.delenv(SP.EXCUSE_ENV, raising=False)
    with pytest.raises(pytest.fail.Exception, match="environment"):
        SP.require("squiddy.index")
    monkeypatch.setenv(SP.EXCUSE_ENV, "1")
    with pytest.raises(pytest.skip.Exception, match=SP.EXCUSE_ENV):
        SP.require("squiddy.index")


def test_part_b_the_pa002_rebuild_test_no_longer_skips_through_importorskip():
    text = (KIT / "tests" / "test_pa002_release_resolve.py").read_text(encoding="utf-8")
    assert 'importorskip("squiddy.index")' not in text
    assert 'require("squiddy.index")' in text
