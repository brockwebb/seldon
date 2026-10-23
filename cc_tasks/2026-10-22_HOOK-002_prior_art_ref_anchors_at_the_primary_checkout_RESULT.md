# RESULT: HOOK-002 (task 09255186), a `prior_art.ref` resolves at the primary checkout, so a worktree commit is judged

**Recall used:** seldon:2026-10-19_PA-002_receipts_verify_against_the_release_they_name_RESULT (the `corpus_anchor` precedent and its worktree fixture, reused). squiddy:2026-10-22_SQ-028R_one_text_of_record_per_document_claims_and_receipts_share_it_RESULT (its 51-file hand run of the gate set the bar the replay had to reproduce, and it did). seldon:2026-10-09_HOOK-001_commit_gate_is_a_hook_not_a_protocol_RESULT (the hook reads the commit as staged, so Part C's replay sets the index to each commit's tree).

**Addenda:** none exist (`*HOOK-002*ADDENDUM*.md`: no match).

## The fix (Part B)

`seldon/core/prior_art.py` `resolve_block`: a relative `ref` now resolves against `corpus_anchor(project_dir)`, the
function ADDENDUM 06 gave the corpus paths. Absolute and `~` refs are unchanged. A ref that does not exist at the primary
is still a `PriorArtError`. From a worktree, the error names the anchored path and the path the ref names when read
from the worktree. No caller changed. `hooks.pre_commit`, `hooks.commit_msg`, `hooks.bypassed`, `seldon prior-art` and
`seldon verify` all reach the ref through `settings`, then `resolve_block`. `hooks.py` was not edited. The change stays
inside the stop condition's two files plus tests.

**Tests, written first:** `tests/test_hook002_ref_anchor.py`, 6 tests. On HEAD, 5 failed and 1 passed: the
non-worktree "one path" message test, which passes by design. The hook tests failed with exactly the squiddy RESULTs'
message (`... names .../proj/.claude/worktrees/seldon/seldon.yaml, which does not exist`). After the fix, all 6 pass.
The tests cover:
- `settings` from a worktree equals `settings` from the primary on every corpus/definition field, including
  `defined_in` (the resolved ref target). The state fields (log, baseline, ledger) are equal relative to each
  checkout. Read literally, "field for field" contradicts ADDENDUM 03 and 06 rule 6, which keep a worktree's state in
  the worktree. The existing PA-002 test asserts that, so the test pins the relative equality.
- A missing ref from a worktree names both paths.
- Through a real installed hook in a linked worktree: a note without prior art is refused for AD-036-R4, not for the
  ref; a note with its staged verdict commits; a commit touching no note commits.

The hook tests put this checkout on `PYTHONPATH` for the hook's `python -m seldon`. Otherwise the hook imports the
pip-installed seldon (the primary's code) and would test main, not the branch.

**Affected suites:** `test_prior_art_ref`, `test_pa002_release_resolve`, `test_hook002_ref_anchor` and `test_hooks`:
56 passed, 1 failed. The failure is `test_rebuilding_the_served_release_reproduces_the_served_index` (real library):
`the index: block of squiddy/graphs/library/extract/control.yaml at edd5d5d66bf2 differs from today's`. This is
squiddy-side state; SQ-028R moved the library index block. It does not touch this change, because `resolve_block`
returns before any changed line for a block with no `ref`, and seldon's block has none. **Full suite:** `python -m dotenv -f .env run -- python -m pytest tests/`. 2790
passed, 2 failed, 7 skipped, in 38m47s. The failures were the real-library test above and
`test_dispatch_stuck_and_journal.py::test_a_project_with_no_dispatch_block_is_left_alone`. The second asserts that
"committed" is absent from `seldon task create` output in a project with no dispatcher. It **passes when run alone**
(1 passed). Its failure in the full run is shared state between tests, and it does not touch `prior_art`.

## Receipts (Part A)

Logged in `docs/design/AD-036_ADDENDUM_08_ref_anchors_at_the_primary.md` section 5. The internal arm ran three queries.
"prior_art ref by reference" hit `docs/decisions/REGISTER.md:9` in seldon and nothing in the other six roots.
"corpus anchor linked worktree" hit ADDENDUM 06:43, which is not cited as a receipt because it would be a
self-citation in the AD-036 family (ADDENDUM 07). The library arm (release sq018_02) holds no source on version-control
working trees; its rows are unrelated. Named prior art: `git-worktree(1)` (one repository, shared refs and config)
and tsconfig `extends` (ADDENDUM 03's origin rule). `seldon prior-art verify --no-record AD-036`: all four of
ADDENDUM 08's receipts **pass**. The family's verdict is still FAIL, on 7 `release_unavailable` library receipts in
ADDENDA 01, 02, 03 and 05 (releases m002 and sq013_01: "`index:` block ... differs from today's") and the known
ADDENDUM 03:106 `self_citation`. Both predate this task.

## Part C: how long it was open, and what the bypass let through

`grep -l -- '--no-verify'` over every `*_RESULT.md` in seldon, squiddy, arnold and ai-readiness-kg. ADDENDUM 06 was
committed `f3e31e1`, 2026-10-20 11:38 -0400. arnold has no `*_RESULT.md`. seldon's only hit is HOOK-001's RESULT
(2026-10-09, before the window), which describes the bypass flag; it does not use it. ai-readiness-kg has none.

| RESULT (squiddy) | Date | Its commits on main | Gate run by hand first, by its own text? | Replayed findings |
|---|---|---|---|---|
| SQ-019 | 2026-10-21 | `869e36d` (36 files), `cd6c96a` (1), `fc1ee35` (6) | Yes: "the same hook functions with the settings anchored at the primary find no gated design note, no register file and no finding" | 0, 0, 0 |
| SQ-029R | 2026-10-22 | `2d7385d` (8; the RESULT's `5199614` before rebase), `1f0c3e0` (6) | No: it argued from content ("holds no design note, no register file and no finding") | 0, 0 |
| SQ-028R | 2026-10-22 | `9065eb7` (51), `563e416` (2) | Yes: `docs/evidence/sq028r/commit_gate.py`, 51 staged, 0 findings | 0 (51 staged, matching), 0 |
| SQ-022 | 2026-10-22 | `e7373ed` (27), `af8e40e` (2), `80b1fe9` (1) | Partly: verified its addendum's receipts through a /tmp `KLUDGE` with the ref anchored; it did not record a gate run | 0, 0, 0 |
| SUITE-001 | 2026-10-22 | `0bdda88` (2), `6d90304` (1), `933db29` (1) | No: it argued from the staged set (no note, register record or finding) | 0, 0, 0 |

**The full measure, not just the named commits.** Every worktree commit in a referencing repository was refused, so
`docs/evidence/hook002/replay_gate.py` replays the fixed gate over **every** non-merge commit on main since
`f3e31e1`. It ran in squiddy, ai-readiness-kg and arnold, each in a `--shared` scratch clone, from a linked worktree
inside the clone. HEAD sat at the commit's parent, the index at the commit's tree, and the commit's own message went
to `commit_msg`. Result: **130 commits (squiddy 99, ai-readiness-kg 27, arnold 4), 0 findings, 0 errors.** Gated
material was in the window. DN-049 and its register records (`633e6aa`, `7b83263`, `84300a5`), DN-043 ADDENDUM 03
(`08f2ed6`), DN-025 ADDENDUM 01 with R-216 (`9065eb7`) and DN-049 ADDENDUM 01 with R-217 (`e7373ed`) were all judged
and passed. **Positive control:** a design note with no prior-art section, planted in the same squiddy replay
worktree, is refused (`no prior-art verdict for its current bytes`). The zero is a measurement. Rows:
`docs/evidence/hook002/replay_2026-10-22.jsonl`. The first run timed out at the session's 10-minute tool limit after
arnold's third commit. arnold was rerun alone (4 of 4), and its rows replace the partial ones.

The bypass let nothing through. As the task says, that was luck, not a control. Three of the five sessions did not
run the gate by hand.

## Premises and task text that were wrong

- All four premises held as stated.
- The task says ADDENDUM 06 is "`corpus_anchor`". ADDENDUM 06 is titled "a library receipt is re-run against the
  release it names"; `corpus_anchor` is its section 2 rule 6. The substance is right.
- "settings ... equals ... field for field" cannot hold for the project's own state fields without breaking
  ADDENDUM 03 and 06 rule 6. It was tested as equality of the definition fields plus relative equality of the
  state fields (above).
- "A ref that does not resolve at the primary either": there is one resolution, at the anchor. The worktree reading
  is not tried; it is only named in the message (ADDENDUM 08 section 3, first alternative, says why).

## Found, not fixed (outside the stop condition's files)

- `seldon/core/dispatch.py` `resolve_standing_band` reads `standing_band_ref` as `project_dir / rel`, the same
  worktree-relative pattern. seldon's own `standing_band_ref: ../squiddy/squiddy/spend.yaml#...` would name
  `.claude/worktrees/squiddy/...` if resolved from a worktree. The standing dispatcher runs in the primary checkout,
  which is probably why nothing has failed. I only read the code; I did not search for a recorded failure. It is the
  same defect class and wants the same anchor.
- The 7 `release_unavailable` receipts in AD-036 (above). The library `index:` block changed after releases m002 and
  sq013_01, so ADDENDUM 06's rebuild refuses them. The real-library PA-002 test fails for the same reason on sq018_02.
  This needs its own task (squiddy library side, or a ruling on rebuilds across an index-block change).

## Deliverables

- `seldon/core/prior_art.py` (the fix), `tests/test_hook002_ref_anchor.py`.
- `docs/design/AD-036_ADDENDUM_08_ref_anchors_at_the_primary.md`.
- `docs/evidence/hook002/replay_gate.py`, `docs/evidence/hook002/replay_2026-10-22.jsonl`.
- Commits on `worktree-binary-stirring-otter`. Not merged, pushed or completed, per the session's instruction.

**Tokens:** 0.14M at the Part C mark (`part-complete`: 140,757; Part B mark 131,619), against the 0.2M estimate and the 0.24M stop.
