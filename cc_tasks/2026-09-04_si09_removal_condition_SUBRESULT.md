# SI-09 removal condition — fleet measurement (LANE F)

**Date:** 2026-09-04
**Graph task:** `1581c3ec` — "Remove the SI-09 transitional units fallback once all
projects report zero fallback resolutions"
**Parent:** `cc_tasks/2026-09-04_seldon_open_defect_closeout.md`
**Decision:** **NOT REMOVED.** The fallback and every line of it stays. See §5.

---

## 1. What was being measured

`seldon/paper/build.py` carries a TRANSITIONAL (AD-028) path that resolves a
`{{result:NAME:...}}` token against the `units` property of an *unnamed* Result,
because before AD-028 `seldon result register` had no `--name` flag and authors
stashed the token key in `units`. It comprises `build_units_fallback_index`, its
call site in `build_paper`, and the `units_fallback` parameter of
`resolve_references`. A resolution through it emits check id **SI-09**.

The removal condition, as written in the module's own comment, has **two**
conjuncts:

> ...once `seldon result migrate-names` has been run live against **every project
> graph** *and* **no build emits an SI-09 line**.

Both must hold. The graph task states only the second. §5 turns on the first.

## 2. Method

One instrument, all projects — including ai-readiness-kg, which had previously
been measured only by its own shim (`scripts/g1_resolve_results.py --check`).

1. **Project enumeration** — `seldon.core.projects.find_projects`, the same
   discovery `seldon events audit` / `replay-check` use, scanning
   `/Users/brock/GitHub` (depth 3). 14 `seldon.yaml` directories found; 13 are
   real Seldon projects (see §6 on the 14th).
2. **File set** — per project, `git grep -l -F '{{result:'` over **tracked**
   files only. Untracked scratch is not the project's content. 107 token-bearing
   tracked files across 6 projects.
3. **Check mode** — new, added by this lane because none existed:
   `seldon.paper.build.check_units_fallback(project_dir, files)` and its CLI
   `seldon paper check-units-fallback`. It loads the project's named artifacts
   and its fallback index from that project's own graph, resolves each file, and
   tallies SI-09 records. It differs from `paper build` in the three ways a
   fleet survey needs: it reads **any** file list (token prose lives in `docs/`
   and `cc_tasks/`, not only `paper/sections/`), it **writes nothing** and never
   invokes Quarto, and it reports an unreachable project as an **error** rather
   than as a zero. Every graph query it issues is a read; nothing was written to
   any project.
4. **Vacuity guard** — the report also carries `named_artifacts` (artifacts with
   a name in that graph) and `unresolved` (SI-01). A project with an empty graph
   resolves nothing by the fallback *and* nothing by name; without these two
   columns that vacuous zero is indistinguishable from a real one.
5. **Instrument provenance** — the `seldon` console script runs the *main
   checkout's* code, not this worktree's. Every run forced
   `PYTHONPATH=<worktree>` and printed `seldon.paper.build.__file__` first;
   every number below was produced by
   `/Users/brock/GitHub/seldon/.claude/worktrees/open-defect-closeout/seldon/paper/build.py`.
   The first attempt without that import guard failed loudly
   (`ModuleNotFoundError: seldon.core.projects`) rather than silently measuring
   the wrong code.

## 3. Per-project SI-09 table

`files`/`tokens` = tracked token-bearing files and result tokens in them.
`named` = name-bearing artifacts in the graph. `fb_idx` = distinct units keys in
the fallback index. `SI-09 res` / `amb` = fallback resolutions and ambiguities.
`SI-01` = tokens that matched nothing by any route.

| project | database | files | tokens | named | fb_idx | **SI-09 res** | **amb** | SI-01 | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ai-readiness-kg | `seldon-ai-readiness-kg` | 20 | 265 | 3859 | 0 | **0** | 0 | 21 | measured |
| leibniz-pi | `seldon-leibniz-pi` | 52 | 146 | 58 | 0 | **0** | 0 | 50 | measured |
| seldon-self | `seldon-seldon-self` | 31 | 122 | 0 | 0 | **0** | 0 | 143 | measured |
| brock-projects | `seldon-brock-projects` | 2 | 1 | 0 | 1 | **0** | 0 | 1 | measured |
| ai-workflow-design | `seldon-ai-workflow-design` | 1 | 1 | 15 | 0 | **0** | 0 | 1 | measured |
| icsp_notebook | `seldon-icsp-notebook` | 1 | 0 | 29 | 33 | **0** | 0 | 4 | measured |
| TickBiteRisk | `seldon-tickbiterisk` | 0 | 0 | 0 | 10 | **0** | 0 | 0 | measured, no tokens |
| arnold | `seldon-arnold` | 0 | 0 | 0 | 0 | **0** | 0 | 0 | measured, no tokens |
| book_responsible_ai | `seldon-book-responsible-ai` | 0 | 0 | 0 | 0 | **0** | 0 | 0 | measured, no tokens |
| census-web-concept-inventory | `seldon-census-web-concept-inventory` | 0 | 0 | 0 | 0 | **0** | 0 | 0 | measured, no tokens |
| federal-survey-concept-mapper | `seldon-federal-survey-concept-mapper` | 0 | 0 | 0 | 0 | **0** | 0 | 0 | measured, no tokens |
| sas2graph | `seldon-sas2graph` | 0 | 0 | 1 | 1 | **0** | 0 | 0 | measured, no tokens |
| usai-harness | `seldon-usai-harness` | 0 | 0 | 0 | 0 | **0** | 0 | 0 | measured, no tokens |
| webdesktop/services | *(none)* | — | — | — | — | — | — | — | **not a Seldon project** — see §6 |

**Fleet totals: 0 SI-09 resolutions, 0 SI-09 ambiguities, across 535 result
tokens in 107 tracked files in 13 project graphs.** No project could not be
measured. ai-readiness-kg's previously reported zero is **confirmed by Seldon's
own resolver**, not only by its shim.

## 4. The AD-028 migration backlog — the number the table above hides

A zero in the SI-09 column means "nothing *cites* a units-keyed Result today". It
does not mean "migrate-names has been run here". Those are different facts, and
the removal condition needs both. Counting Results directly:

| project | Results | named | **unnamed** | fallback-reachable rows |
|---|---:|---:|---:|---:|
| ai-readiness-kg | 3859 | 3859 | **0** | 0 |
| leibniz-pi | 53 | 53 | **0** | 0 |
| **icsp_notebook** | 346 | 0 | **346** | 183 |
| **TickBiteRisk** | 61 | 0 | **61** | 61 |
| **brock-projects** | 2 | 0 | **2** | 2 |
| **sas2graph** | 2 | 1 | **1** | 1 |
| ai-workflow-design, arnold, book_responsible_ai, census-web-concept-inventory, federal-survey-concept-mapper, seldon-self, usai-harness | 0 | 0 | 0 | 0 |

**410 unnamed Results remain in 4 of 13 project graphs.** `seldon result
migrate-names` has been run live in exactly two: ai-readiness-kg and leibniz-pi.

Those four score zero SI-09 for a reason that is not migration completeness:
three of them (TickBiteRisk, brock-projects, sas2graph) have **no token-bearing
tracked prose at all**, and icsp_notebook's single token-bearing file contains no
token that matches the AD-028 name grammar. Their zero is "nobody has written the
prose yet", not "the legacy rows are gone".

A note on `fb_idx` for the reader who checks this later: the index is
deliberately over-inclusive — it holds every unnamed Result whose `units` is not
in the packaged vocabulary. In these four projects much of that population is
genuine units the vocabulary lacks (`percent`, `pp`, `spearman_rho`,
`tests_passed`) rather than stashed token keys. That does not soften the
conclusion — those rows are unnamed either way, and the fallback is what an
author would hit — but it means `fb_idx` should not be read as "known legacy
token keys".

## 5. Decision — the fallback stays, and why

Every measured project reports zero SI-09 resolutions. The second conjunct of the
removal condition holds. **The first does not**, and it is not a formality:

1. **`migrate-names` has not been run against every project graph.** 410 unnamed
   Results in 4 graphs (§4). The condition names this explicitly and it is
   plainly false today.
2. **The fleet zero is an artifact of absence, not of migration.** The four
   unmigrated projects score zero because they have no prose citing Results yet.
   The first `{{result:...}}` token any of them writes lands on an unnamed
   Result. With the fallback present that is a non-fatal SI-09 warning naming
   the fix; with it removed it is a hard SI-01 build failure with no transitional
   path. Removing a safety net *before* the population it protects is migrated
   inverts the point of the net.
3. **The measurement is scoped to tracked files, by design.** Untracked drafts in
   those four projects were deliberately out of scope. "Zero" is therefore a
   statement about tracked content, which is the right scope for the survey but
   not a warrant for a one-way deletion.
4. **The asymmetry is one-sided.** Keeping the path costs a warning branch that
   currently never fires. Removing it early costs four projects a broken build at
   the worst moment. Nothing else depends on the path, so it can be deleted in
   one commit whenever the condition is genuinely met.

**Blocked by, with counts to clear:**

| blocking project | database | unnamed Results to name |
|---|---|---:|
| icsp_notebook | `seldon-icsp-notebook` | 346 |
| TickBiteRisk | `seldon-tickbiterisk` | 61 |
| brock-projects | `seldon-brock-projects` | 2 |
| sas2graph | `seldon-sas2graph` | 1 |

**What must become true for removal to proceed:**

1. `seldon result migrate-names` run live in each of those four project graphs,
   until `MATCH (r:Result) WHERE r.name IS NULL RETURN count(r)` is 0 in all 13.
2. The §3 table re-run with `seldon paper check-units-fallback` and still all
   zero, with `fb_idx` = 0 everywhere (no Result reachable only by units).
3. Then delete, in one commit: `build_units_fallback_index`, its call site in
   `build_paper`, the `units_fallback` parameter of `resolve_references` and the
   SI-09 branch inside it, `UNITS_FALLBACK_CHECK_ID`, the SI-09 tests in
   `tests/test_paper_build.py`, **and the instrument itself** —
   `check_units_fallback`, `UnitsFallbackReport`, `UnitsFallbackFileCount`, the
   `seldon paper check-units-fallback` command, and `tests/test_si09_check.py`.
   An instrument for a retired condition is dead weight.

Until then the graph task `1581c3ec` should be **annotated, not closed**: the
condition is measured, unmet in its first conjunct, and the blocking set is named
above.

## 6. Incidental finding — `find_projects` false positive (not fixed here)

`/Users/brock/GitHub/webdesktop/services/seldon.yaml` is **not a Seldon project
config**. It is a webdesktop service definition for a service *named* "seldon"
(`name: seldon`, `subdomain: seldon`, `port: 8765`, `start_command: ... scripts/
observability_dashboard.py`). `seldon.core.projects.find_projects` treats any
directory holding a file called `seldon.yaml` as a project, so it is reported as
a project with no `neo4j.database`.

Consequence for this survey: none — it is excluded as a non-project rather than
counted as an unmeasurable one, so no genuine project went unmeasured. Left
unfixed here because `seldon/core/**` is outside this lane's file ownership. The
fix is a shape check (require a `project:` or `neo4j:` key) in `load_project_ref`,
and it is worth doing before anything acts on the fleet inventory automatically.

## 7. Files changed

| file | change |
|---|---|
| `seldon/paper/build.py` | **added** `UnitsFallbackFileCount`, `UnitsFallbackReport`, `check_units_fallback`; extended the REMOVAL CONDITION comment to name the instrument and point at this file. **The fallback itself is untouched.** |
| `seldon/commands/paper.py` | **added** `seldon paper check-units-fallback` (exit 0 = measured zero, 1 = measured non-zero, 2 = not measurable). |
| `tests/test_si09_check.py` | **new**, 11 tests. |
| `cc_tasks/2026-09-04_si09_removal_condition_SUBRESULT.md` | this file. |

No file in the SI-09 fallback path was deleted or edited.

**Suite: 1391 passed, 0 failed** —
`python -m dotenv -f .env run -- python -m pytest tests/ -q`.

## 8. Reproducing the measurement

```bash
# per project, from that project's root:
git grep -l -F '{{result:' > /tmp/tracked.txt
seldon paper check-units-fallback --files-from /tmp/tracked.txt --verbose
# exit 0 = zero SI-09; 1 = non-zero; 2 = project not measurable
```

Run it from a checkout whose `seldon` on PATH is the code under test, or force
`PYTHONPATH` and print `seldon.paper.build.__file__` first. The console script
resolves to the main checkout, and a measurement taken against the wrong code is
worse than no measurement.
