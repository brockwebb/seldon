# SEL-063: recall's selection and audit, configuration that names one machine, and the smaller review findings

**Status:** proposed
**Author:** REVIEW-001 (a dispatched session that did not write the reviewed code), 2026-11-28, from its findings record.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** 2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc
**Found in:** seldon:docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md#F-23
**Governing:** the recall design note and its R-records (RECALL-001 names them), AD-033-R16 (the binding prune), AD-036 (prior art), the constitution's sections 2 (never hardcode) and 15 (checkpointed work).
**Prior art:** named per finding in the review record. Section 15's checkpoint/restart rule (unit keys derived from every input) for F-26; `git log --diff-filter=A` as the record of when a file landed for F-25.
**Spend:** est. 800k tokens.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** seldon/core/recall.py, seldon/core/recall_audit.py, seldon/core/decisions.py, seldon/core/prior_art.py, seldon/commands/cc.py, seldon/core/hooks.py, scripts/sel056/, seldon.yaml, pyproject.toml, README.md, tests/
**Parts:** A 0.5, B 0.5.

REVIEW-001 found these in the code merged between e42c25bc and 078b80d0 (`**Found in:**` names the first; this task remediates F-23 to F-33, each an Issue). None is of a class it may fix itself. Each finding is an Issue (`seldon issue list --type review_finding`); a fix names its finding's Issue and carries a test that fails first.

## Part A: recall and the graph (F-23 to F-27)

- F-23 (pre-existing, outside the reviewed diff): `seldon cc rederive-description` without `--dry-run` calls `update_artifact`, which `seldon/commands/cc.py` never imports (`seldon/commands/cc.py:2191`; pyflakes: undefined name).
- F-24: recall's stage 4 (dead ends) reads the Issue threshold, `lexical_min_shared_terms.get("issue")`, not its own kind's, which `seldon.yaml` sets to null (`seldon/core/recall.py:855`).
- F-25: `recall_audit` dates a RESULT's landing by the file's mtime, which a clone or rebase resets (`seldon/core/recall_audit.py:552`).
- F-26: `recall_audit`'s checkpoint key leaves out the recall block, which decides both sides of the replay, so a changed block resumes stale rows (`seldon/core/recall_audit.py:538`, `:556`).
- F-27: `seldon verify --fix` ends `constrained_by` edges from completed tasks to records superseded since, and reads the projected state, which leaves out pending acceptances (`seldon/core/decisions.py:1880-1905`). The removals are recorded (`link_removed`), so nothing is lost; decide whether terminal tasks keep the edge as history.

Acceptance:
- `check: python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -k "sel063 and part_a"` passes.

## Part B: configuration and adopters (F-28 to F-33)

- F-28: `prior_art.internal_roots_from: ../factory/seldon.yaml#portfolio.repositories` raises when there is no sibling factory checkout, on the commit hook, `verify` and `cc register` paths (`seldon/core/prior_art.py:385-386`, `seldon.yaml:107`); the same reference backs `recall.audit.repositories_from`.
- F-29: `dispatch.hive.mint_command` names one machine's interpreter and checkout (`seldon.yaml:414-416`).
- F-30: `scripts/sel056/*.sh` `rm -rf` an unchecked argument and hardcode one machine's squiddy interpreter (`scripts/sel056/trial.sh:8`, `scripts/sel056/sq.sh:5`); harden them or remove them now SEL-056's evidence is recorded.
- F-31: the shipped `gate_command` needs `pytest-xdist` (`-n 6`) and its comment relies on `pytest-randomly`; neither is declared in `pyproject.toml`'s `dev` extras, and the README has no install section.
- F-32: the hooks-path repair rests on the Claude Code CLI's rewrite of `core.hooksPath` (`seldon/core/hooks.py:353-388`); keep the per-worktree value and treat the shared one as advisory in `status()`.
- F-33: `tests/test_pa002_release_resolve.py` now builds its own fixture but still skips through `importorskip("squiddy.index")`, so a gate without squiddy passes without running it.

Acceptance:
- `check: python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -k "sel063 and part_b"` passes.
- `check: test -f cc_tasks/2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings_RESULT.md` passes.

**This task may not:** touch another repository (factory's portfolio file is read, never written).
