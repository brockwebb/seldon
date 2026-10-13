# MODEL-002 ADDENDUM 02: identity, scope (Anthropic models only), and the squiddy guard

**Date:** 2026-10-13. **Authored by:** Desktop session, on the operator's direction of the same day.
**Amends:** the base task and ADDENDUM 01. Read all three before any step.

## 1. Identity

`cc_tasks/2026-10-09_MODEL-002_explicit_effort_hermetic_model_tests.md` already holds the label MODEL-002. This task is **MODEL-003**. The RESULT, the decision records' source notes, commit messages and the addendum note use MODEL-003. The file names stay as registered; the ResearchTask id is `019844b9`.

## 2. Scope: Anthropic models only

The operator's direction: the MVP reaches initial operational capability on Anthropic models only. Nothing in this task adds, calls, configures or depends on a non-Anthropic model or a third-party router.

- ADDENDUM 01 cites OpenRouter's `supported_parameters` as prior art for the *shape* of a per-model parameter profile. It is a citation, not a dependency: no OpenRouter code, client, key, endpoint or test.
- The catalog holds Anthropic model ids only (`claude-*`). `load_registry` refuses any other prefix, so a non-Anthropic entry cannot slip in before its own task decides how it should work.
- Non-Anthropic providers are backlog, recorded as their own ResearchTask (FUTURE, risk-driven, low urgency).

## 3. The squiddy guard

The registry and lock are machine-wide (AD-035-R1). Squiddy's extraction daemon, model client and quality controls resolve their roles through `seldon.models`, as do ai-readiness-kg, arnold and icsp_notebook. A change to the registry's shape must not move any of them.

- check: before the change, record `seldon models resolve <role> --json` for every role in `models/registry.yaml`; after it, the same command gives the same model id, effort and CLI for every one of them. Quote both tables' sha256 in the RESULT.
- check: squiddy's model-client tests pass against the changed seldon, run read-only from `/Users/brock/GitHub/squiddy` (no commits there); quote passed, skipped, xfailed, deselected, failed.
- If either check moves or fails, stop before merging and report. Do not edit squiddy.

## 4. Dirty tree at registration

The dispatcher refused this task for c7 (dirty tree) from 2026-10-12T13:13Z. Its log names `state/prior_art_queries.jsonl`, `cc_tasks/2026-09-28_designnote_cites_citation.md`, this task's two addenda and `docs/evidence/model001/refresh_2026-10-12.json`. Step 0: report in the RESULT what each of those was (who wrote it, whether it was committed by the operator before launch) so the next registration does not repeat it.
