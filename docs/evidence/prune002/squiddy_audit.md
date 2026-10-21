# PRUNE-002 Part C: squiddy CLAUDE.md audit (2026-10-20)

`/Users/brock/GitHub/squiddy/CLAUDE.md` before the cut: 10,068 bytes, 157 lines, at squiddy `c36cbea`. Each block is
sorted into one of four buckets: **enforced** (a mechanism refuses the violation, named here), **stale**,
**duplicate** (of `~/GitHub/CLAUDE.md`, of `README.md` or of a governing doc), or **needed**. Paths are squiddy's
unless they start with `seldon/`. The mechanism lookup was read-only, by grep and reading, on 2026-10-20.

| Lines | Content | Bucket | Mechanism or reason |
|---|---|---|---|
| 1-3 | title, "read this first", placeholder name | needed (title kept) | the "read first" line is how the CLI already loads the file |
| 5-11 | what this is: a kit, not a system | duplicate | `README.md` opening paragraphs; one identity line kept |
| 13-18 | prior art: ODK/ROBOT, Monarch, Seldon AD-002, ai-readiness-kg | duplicate | `README.md` names ODK/ROBOT, Monarch, LinkML, KGX, Koza, KG-Hub |
| 20-26 | relationship to Seldon | duplicate | `README.md` ("Squiddy is to Seldon what ROBOT is to the ODK") |
| 28-38 | the one invariant; the ledger is authoritative, Neo4j is a replay | needed (compressed) | partly enforced: parity gate (S-009, H-001); `squiddy/records.py:206` "the records log and the manifest disagree". The statement of the invariant is what every gate is checking, so it stays in two sentences |
| 42-43 | CONOPS pointer | needed | pointer |
| 45-46 | spec over design note | needed | no mechanism |
| 48-51 | the extraction spec is amended in the same commit | needed | **none found**: no hook or test names `EXTRACTION_DESIGN_SPEC.md`; `seldon/core/hooks.py` `pre_commit` checks prior art, decisions and labels only |
| 52-55 | methodology is re-copied, never edited in place | needed | **none found**: no hash or copy check (item 37 `fixture_copies` covers `tests/fixtures` only) |
| 56-57 | S-008 pre-registrations never edited | needed | partial only: `tests/test_label_matchability.py:96-100` and `tests/test_extraction_context.py` pin some wording; other edits pass |
| 58-60 | design notes and DI rows, as pointers | needed (compressed) | pointers |
| 62-73 | two-part Prior art section | enforced | `seldon/core/prior_art.py:1325` `missing: no ## Prior art section (AD-036-R1)` and `:1337` (no External or Internal subsection), run at commit by `seldon/core/hooks.py:402` `prior_art_findings` from `.githooks/pre-commit`; a `draft:` commit is held by the dispatcher as `governing_unverified` (`seldon/core/dispatch.py:1792`) |
| 75-76 | "the Seldon gate ... is NOT BUILT" | stale | the gate above is built. Issue `2f46e15a` is still open in `seldon_events.jsonl` (only `artifact_created`, 2026-09-20) and should be closed by whoever owns it; this task does not change its state |
| 80-87 | extract, do not design; adopt, harvest or reject; no RDF/OWL rewrite | duplicate, plus one needed line | `~/GitHub/CLAUDE.md` §1, §7 and §7.5 cover adopt-before-create and prior art; the property-graph-plus-LinkML decision is project-specific and stays in one line |
| 88-90 | the manifest is the only way into a graph | enforced | `squiddy/manifest.py:79` "FATAL: ... is not in the manifest"; `squiddy/gates.py:149` `manifest_leg` (`manifest-presence:`); `squiddy/records.py:206` |
| 91-96 | an admitted entry can be re-assessed; retractions fold in ledger order | enforced | `tests/test_reingest.py:99` `test_a_child_retracted_then_asserted_again_is_live` (and :108, :114); `tests/test_q003_write_update.py:65`; `tests/test_ledger_manifest.py:32` |
| 97-98 | public-only is a per-graph policy | enforced | the assessment stage applies the graph's declared policy (the line itself says so) |
| 99-100 | only extraction calls a model; the client is named in config | stale (first half), enforced (second half) | stale: the quality and judge sites call models too. Enforced: item 26 `calls_through_the_layer` (`squiddy/conformance.py:2183`), item 35 `spend_governed` (:3148), item 36 `configs_name_roles` (:3248) |
| 101-102 | QC rules come from defects, with report and date; no human review is a gate | enforced, plus duplicate | the `Gate` fields `source` and `lesson` (`squiddy/conformance.py:132-133`), required by `tests/test_x001_conformance.py:89-92`; "gates bind the machine" is `~/.claude/CLAUDE.md` §3 |
| 103 | green is done for CI; the run URL is the evidence | stale | there is no `.github/workflows`; the nearest check is `squiddy/kitpass.py` `kit_commit_untested` |
| 104-106 | maintenance is scheduled stages with gates | duplicate | `docs/CONOPS.md` (maintenance as a product function, DN-023) |
| 107-108 | the kit's acceptance bar (Brock, 2026-09-10) | needed | an operator ruling, no mechanism |
| 109-111 | first and second consumers | stale | history; the graphs exist under `graphs/` and their DNs record it |
| 112-118 | one graph, one run; `control.yaml` keys; status; STOP | enforced, plus the operating commands kept | `squiddy/factory.py:94` `EXIT_STOP = 3`; item 21 `factory_stop_lands_in_flight` (`squiddy/conformance.py:1749`); item 24 `factory_missing_key_fatal` (:1891, `FactoryFatal`); status from `factory/status.json` (`squiddy/factory.py:81`, `tests/test_f001_factory.py:248`). The run, stop and status commands stay in one line, because an agent needs them to operate |
| 119-120 | four pause touchpoints | enforced | the factory's pause records (DN-026, DN-028) |
| 122-138 | external calls are checkpointed | enforced, plus duplicate | `~/GitHub/CLAUDE.md` §15; item 26 `calls_through_the_layer` (`squiddy/conformance.py:2183`, exempt list `call_layer.exempt`); item 27 `kill_test_no_key_twice` (:2261, a real SIGKILL) |
| 140-145 | autonomy L4 | needed (compressed) | project-specific. The operator-entry list duplicates `~/.claude/CLAUDE.md` §2 and is cut to a pointer |
| 147-152 | secrets | enforced, plus duplicate | `squiddy/secrets.py`, the one accessor (`tests/test_secrets.py`); `squiddy/secret_scan.py`, run on Desktop commits by `seldon/core/desktop_commit.py:188` `secret_found`; `.env` gitignored is `~/GitHub/CLAUDE.md` §3 and §6 |
| 154-156 | vocabulary ban | needed | **none found**: no linter for "load-bearing", "hallucinate" or em dashes |

**Gaps found, not fixed here:** rules 48-51, 52-55 and 56-57 have no mechanism or only a partial one, and the
vocabulary ban has none. They stay in the file because nothing else carries them. Each one is a candidate for a
check (a hook or a conformance item), which would let it leave the file the way the others did.

After the cut: see `measurements.md` (Part C).
