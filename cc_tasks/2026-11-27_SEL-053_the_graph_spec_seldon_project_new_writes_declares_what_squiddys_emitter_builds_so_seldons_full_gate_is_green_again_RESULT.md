# RESULT: SEL-053. The graph spec `seldon project new` writes declares what squiddy's emitter builds

- **Part A done.** The skeleton `seldon/templates/graph_spec/squiddy_graph.yaml` now declares Work and the four
  classes squiddy's seeded emitter builds when it writes a Work: `Person: Node`, `Organization: Node`,
  `AuthoredBy: Edge`, `AffiliatedWith: Edge`. These are the parents squiddy's refusal names. The order is squiddy's
  `tests/test_init.py` `WORK_WRITE`. With that change, `test_the_real_squiddy_initializes_a_filled_skeleton` passes
  against squiddy main (`8821fb9e`).
- **The refusal says what it is.** `graph_step` (`seldon/core/project_new.py`) now reads the spec and lists the
  operator fields still blank (`GRAPH_SPEC_OPERATOR_FIELDS`: title, description, scope.topic), and asks for only
  those. If all three are filled, the refusal is reported as `squiddy init refused <spec>: <squiddy's last line>.`
  and gives no fill advice. Code: `blank_operator_fields`.
- **Acceptance:** `/opt/anaconda3/bin/python -m pytest tests/test_sel019_project_new.py -q -p no:cacheprovider`
  (with `.env` loaded through `python -m dotenv`, and `PYTHONPATH` set to this worktree so the branch's code is
  what runs): **16 passed in 61.78 s**. I did not run the full suite here. The merge gate runs it, and that run is
  what clears SEL-051.

**Date:** 2026-11-27. **Branch:** `worktree-lexical-jumping-steele`, from main `24d3b82`. The fix is commit
`4e1e616`; this RESULT is in the commit after it. This session did not merge, push or complete the task, and did not
redrive SEL-051. **Addenda read:** none exist (no `*SEL-053*ADDENDUM*` file).
Recall used: squiddy:2026-11-26_SQ-146_init_refuses_a_spec_its_emitter_cannot_write_and_an_acquire_halt_from_a_missing_archive_directory_clears_when_the_directory_exists_RESULT

The SQ-146 RESULT is the source for the four classes, their parents, and the "refuse, not seed" reasoning that ruled
out seeding them on the squiddy side. The other recall hits (AD-030 ingest, SQ-090R, K-001 defect 4, SEL-005,
SEL-050) did not change the approach.

## Premises re-checked

- Reproduced the failure on this branch's base before changing anything. The real-squiddy test failed. I also
  wrote two new tests (below), and both failed before the fix: **3 failed, 2 passed**.
- `squiddy init --help` (squiddy main) has no option that prints the classes an emitter needs. The requirement
  lives only in squiddy's Python: `squiddy/init.py` `write_requirements` / `unwritable`, which read the emitter's
  syntax tree.

## Step 1: declare the four, not `primary_class_by_kind: {work: null}`

A graph made by `seldon project new` is a corpus graph, and squiddy calls Work "one admitted source document". It
holds Works, so `work: null` would make a skeleton that cannot admit anything. The first fix squiddy names is the
right one.

## Step 2: one source. I kept the four in the template, pinned by the real-squiddy test

What I considered:
1. **Import squiddy in seldon and render the classes when the skeleton is written**
   (`squiddy.init.write_requirements(EMITTER_TEMPLATE, ["work"])`). Rejected. SEL-019 drives squiddy only through
   its command (`project_new.squiddy_command`, run as a subprocess), and seldon does not depend on squiddy as a
   package. This choice would add that dependency to fill in four lines of text.
2. **Ask squiddy's CLI.** Not possible. No command prints the requirement. `init --check`'s `emitter-cannot-write`
   reads an existing graph's emitter, not a spec before init. Adding such a command would mean changing squiddy, and
   this task forbids that.
3. **Write the four in the template, and use the existing real-squiddy test to catch drift.** Chosen. Squiddy's
   refusal stays the single authority: if squiddy's emitter changes what it builds, `init` refuses the skeleton and
   `test_the_real_squiddy_initializes_a_filled_skeleton` goes red, naming the classes. That test is how this drift
   was found. The template's comment cites SQ-146 and the test.

This is the same split squiddy uses: the class list is written by hand (its own tests keep it in `WORK_WRITE`),
and `init` checks it. **No new decision was written.** SEL-019 set the design (subprocess boundary, skeleton
template) and SQ-146 set the rule (refuse at init, the spec is the one declaration). AD-037-R15 is about the
interpreter a check runs under, not `project new`, and no AD governs the template's content. The template lists
what squiddy's rule requires, so it is not a new rule for seldon.

## Step 3: tests (written red first)

- `test_a_refusal_of_a_filled_spec_is_squiddys_own_line_with_no_fill_advice`: a stub squiddy refuses a filled
  spec. Its reason is on the last line of stderr, after a line that is not the reason. Before the fix the detail
  said `... Fill graphs/demo/graph.yaml (title, description, scope.topic ...)`.
- `test_a_refusal_of_an_unfilled_spec_names_only_the_fields_still_blank`: when description is filled and title
  and scope.topic are still blank, the advice names only `title, scope.topic`.
- `test_the_real_squiddy_initializes_a_filled_skeleton`: unchanged in what it asserts. It now uses the shared
  `_fill` helper.

## Step 4: what reads the template

Only `seldon/core/project_new.py` (`GRAPH_SPEC_TEMPLATE`, `graph_step`), called from
`seldon/commands/project.py:142`, and `tests/test_sel019_project_new.py`. That whole file passes (16 of 16, above).

## Step 5: projects that carry the old skeleton

**None.** I read every `graph.yaml` under `~/GitHub/*/graphs/*/` (10 specs) and, for each one, the version in the
commit that added it (`git log --diff-filter=A`). None began as the skeleton: none carries its "Written as a
SKELETON by `seldon project new`" header. Each was written by its own task (factory FAC-01, critical-thinking-ai
CTAI-004, aacps AP-01, hazbrief HB-01b, arnold KG-001, ai-readiness, seldon SEL-036, squiddy's three). I changed
none of them.

Separately from the skeleton, the four classes are still missing in factory `factory-kg`, hazbrief-mcp
`hazbrief-corpus`, aacps-ai-policy `aacps-policy-dm`, ai-readiness-kg `ai-readiness`, and squiddy `graphs/registry`
(all four missing). squiddy `graphs/library` lacks Organization and AffiliatedWith. SQ-146's RESULT already reported
this for four of these graphs (it did not list ai-readiness or registry), and it is squiddy's survey, not this
task's scope. Listed here, not changed.

Changed: `seldon/core/project_new.py`, `seldon/templates/graph_spec/squiddy_graph.yaml`,
`tests/test_sel019_project_new.py`, and this RESULT.
