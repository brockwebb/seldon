# Filing from factory: the spec check of 2026-11-26 found 3 check(s) of seldon not at spec and needs in the kit

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-26
**Reporter:** factory FAC-15, the spec check's first run (factory `docs/spec_check/2026-11-26.md`, full results `docs/spec_check/2026-11-26.json`; factory F-033, design note `docs/design/2026-11-26_DN-001_a_component_is_at_spec_when_its_installed_and_operating_checks_pass.md`)

## What was run

`scripts/spec_check.py` in factory (branch commit ad8a45b) at 2026-11-26T13:55:43Z, over every registered repository, this one's primary checkout included. Each check below is this repository's or the kit's own command, run in this directory with a timeout; it wrote nothing here (no cache, no bytecode). Where factory ran a probe of its own (`factory/scripts/spec_probe.py`), the owner had no command for it; the probe is a key or file test, or a call into the owner's own loader.

## What came back

### systems engineering documents: `projections_declared` is WARNING

- Ran (installed stage): `/opt/anaconda3/bin/python factory/scripts/spec_probe.py keys seldon.yaml docs.projections`
- Came back: exit 1; the line reported: "seldon.yaml has no docs.projections"
- At spec: exit 0. Where that is written: the operator, 2026-11-26 item A: "all projects require systems engineering documents" (docs/2026-11-26_operator_dictation_spec_check_catalog_names_roles.md); seldon AD-013-R2 (projections declared in docs.projections)

### seldon project: `seldon_verify` is CRITICAL

- Ran (operating stage): `seldon verify`
- Came back: exit 2; the line reported: "✗ File hashes           2 modified: 2026-09-15_standing_dispatcher.md, AD-036_ADDENDUM_01_self_test.md — run `seldon paper sync`"
- At spec: exit 0 is OK, 1 is WARNING, 2 is CRITICAL; OK is at spec. Where that is written: constitution section 14 (`seldon verify` after an edit to a tracked artifact); seldon verify's own exit codes

### seldon project: `seldon_yaml_project_new_blocks` is WARNING

- Ran (installed stage): `/opt/anaconda3/bin/python factory/scripts/spec_probe.py keys seldon.yaml environment.packages desktop_commit.scan.command decisions.repository`
- Came back: exit 1; the line reported: "seldon.yaml has no environment.packages"
- At spec: exit 0. Where that is written: seldon SEL-019 (`seldon project new` writes environment and desktop_commit.scan); seldon AD-033-R13 (a project with no decisions block is reported, and project new declares one)

## What was experienced beyond the table

- `seldon project new` writes no `prior_art:` block: `seldon/core/project_new.py` has no prior-art step, and its docstring lists none. factory (FAC-15 Part A) and critical-thinking-ai (CTAI-003) each added theirs by hand, in the referencing form; aacps-ai-policy still has none (its filing of the same date).
- `core.hooksPath` holds an absolute path in the primary checkouts of factory (`/Users/brock/GitHub/factory/.githooks`) and critical-thinking-ai (`/Users/brock/GitHub/critical-thinking-ai/.githooks`), so `seldon hooks status` exits 1 and `seldon verify` reports the commit hook not installed in both. `seldon/core/hooks.py` `point_worktree` records the same in seldon and squiddy (SEL-012), "written by something outside seldon". Both repositories are dispatched into Claude Code worktrees.
- `seldon decision project`, run in a factory worktree after `seldon decision accept` had written `docs/decisions/register/pending/00001_df7c8bd9aebfff86_factory-f-033_accept.yaml`, raised `KeyError: 'record_hash'` in `seldon/core/decisions.py` `last_hash` (line 772). It had projected the numbered records first (two events written); a second run raised the same and wrote nothing.
- Two checks the spec check needed have no seldon command that only reads: that a project's graph database answers, and that a `prior_art:` block resolves (`seldon prior-art verify` records a verdict). Factory calls seldon's own `seldon.config.get_neo4j_driver` and `seldon.core.prior_art.settings` for them (`factory/scripts/spec_probe.py graph-db` and `prior-art`).

## What factory does not know

Whether each finding is already known here, intended, or in hand. A WARNING is a requirement older repositories may predate or the operator's own hold (seldon AD-032 FC-08); it is reported, not lifted. Factory changes nothing in this repository; the spec check runs again at the start of every factory coordinator session, so a finding that is answered here drops off its next report.
