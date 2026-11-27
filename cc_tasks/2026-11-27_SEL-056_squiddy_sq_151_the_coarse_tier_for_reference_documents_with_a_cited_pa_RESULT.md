# RESULT: SEL-056, squiddy SQ-151's coarse tier adopted in seldon-biblio, with a cited passage promotable word for word

**Date:** 2026-11-27. **Branch:** `worktree-compiled-sprouting-squirrel`. **Status:** Part A done. No addendum existed
(`ls cc_tasks/*SEL-056*ADDENDUM*`: none). **Spend:** zero model calls; agent tokens as `seldon dispatch part-complete`
reports them. **Network:** none.

Recall used: none

The recall hits (AD-030 ingest, SEL-004/005 dispatch, squiddy R-110, DI-150, R-37, DI-155) bear on the governed graph
and the dispatcher, not on whether a squiddy graph declares a tier; none changed the approach.

## What was decided, and on what grounding

**Which graph.** The tier is a squiddy graph-spec key (`tiers:` in `graph.yaml`). Seldon has two squiddy graphs:
`governed/` (seldon's own design notes and tasks; a hand-made, pinned config with no `graph.yaml`, copied from a
template) and `graphs/seldon-biblio` (the works, standards and software seldon's rulings cite). The operator's
statement in filing 750348cb is about "documents that are more of a reference, more of a source"; those are
seldon-biblio's entries by its own scope ("the works, standards and software Seldon's design notes and tasks rest
on"). `governed/` holds seldon's own records, which AD-030 already carries as `Passage` and `Citation` artifacts, and
is not a reference corpus. So seldon-biblio adopts; `governed/` does not.

**Which disposition.** SQ-151's example writes `tiers: {coarse: [reference]}`. seldon-biblio has no `reference`
disposition: its manifest holds `active` (84 entries, text held) and `metadata_only` (64, no text). Every held text
in it is a reference document, so the tier is `coarse: [active]`: the same rule, without re-dispositioning 84
in-graph entries (which candidates do not refresh; squiddy R-213). `metadata_only` holds no text and needs no tier.
Full extraction stays available for any one entry by changing its disposition, a recorded manifest edit (R-295
item 3), which is the operator's "I'm not going to completely cut that out". `engine.extract.enabled: false` still
closes extraction for the whole graph (squiddy CONOPS R-106, the spec's header); the tier is the per-entry statement
that survives a future task opening it.

**Why now and not later.** The graph was already drifted: `squiddy init graphs/seldon-biblio --check` on main reported
`drifted schema/seldon_biblio.yaml` and `kit-changed squiddy/schema/base.yaml` before any edit, the whole body
difference being SQ-151's base section comment (the defect squiddy SQ-154 is fixing; see below). Clearing that drift
is a schema epoch whatever seldon decides, so taking `Passage` and `PassageOf` in the same epoch costs nothing extra
and means the first cited passage needs no epoch of its own.

Prior art: the tier and the promotion are squiddy's (DN-050 ADDENDUM 02 R-295: the W3C Web Annotation
TextQuoteSelector, with the lexical-graph and LazyGraphRAG pointers seldon's filing gave). Seldon adopts it as
specified and departs only in the disposition named, for the reason above.

## What was applied

| What | Where |
|---|---|
| `- Passage: Node`, `- PassageOf: Edge`, `tiers: {coarse: [active]}`, each with its basis in a comment | `graphs/seldon-biblio/graph.yaml` |
| `squiddy init graphs/seldon-biblio --render --allow-schema-change` (squiddy main `70695d29`) | `config.yaml` (`engine.tiers`), `schema/seldon_biblio.yaml`, `schema/generated/*`, `.squiddy_init.json`, `.env.example` |
| `squiddy schema declare --graph graphs/seldon-biblio --by SEL-056`: epoch `0.1.0+57282dee675b` (was `0.1.0+de21b9c7ec65`) | `graphs/seldon-biblio/ledger/open.jsonl`, one `schema_declared` line |
| The rehearsal and check scripts this RESULT's numbers came from | `scripts/sel056/` (`sq.sh`, `trial.sh`, `conformance_pair.sh`, `promote_trial.sh`, `drift_survey.sh`) |

`squiddy passage tier --graph graphs/seldon-biblio`: `coarse tier: ['active']; 84 entr(y/ies) held coarse`.

## Proven before the tracked graph was touched

On scratch copies of the primary checkout's seldon-biblio (tracked files plus its gitignored export, 83 parsed texts
and index; `scripts/sel056/conformance_pair.sh /tmp/sel056c`, then `promote_trial.sh /tmp/sel056c`):

- Graph-scope conformance, main as it is vs. adopted: both exit 0, every gate identical except item 42
  `passages_grounded`, N/A on main (no `Passage`) and PASS adopted.
- `squiddy passage promote --id amodei2016concrete --exact "an objective function that is too expensive to evaluate
  frequently"` wrote `passage:amodei2016concrete:410b7fbcaf46` at `[810, 876)`, 2 events; the same promotion again
  appended 0; a quote not in the text was refused (`does not occur in the parsed text`, exit 1); item 42 PASS after.
- `squiddy extract --id amodei2016concrete` was refused, but by `engine.extract.enabled: false`, which is checked
  first; the tier's own refusal is not reachable in this graph while extraction is closed (squiddy's
  `tests/test_sq151_passages_and_tier.py` proves it).

Seldon's tests that read seldon-biblio, on this branch: `tests/test_sel036_library_graphs.py`,
`test_sel036_biblio_bridge.py`, `test_sel039_own_graphs_first.py`, `test_sel037_worktree_links_exports.py`:
39 passed.

## What was not applied, and why

- **No passage was promoted in the tracked graph.** No ruling has asked for one yet; a promotion is made when a
  citation asks (`--for` names it). The command, from seldon's root, after this merges and with the parsed texts the
  primary holds:
  `/Users/brock/GitHub/squiddy/.venv/bin/squiddy passage promote --graph graphs/seldon-biblio --id <entry> --exact "<quote>" --for "<AD-NNN-Rn or SEL-NNN>" --by <who>`.
  A promoted passage is served by the next release (`squiddy release --graph graphs/seldon-biblio`), not before.
- **No release was cut.** The epoch is declared; the served export is unchanged until the next build, and the gates
  above pass on it either way.
- **`45b88039` stays open** (locating a passage without parsing and indexing the whole document); SQ-151 did not
  build it, and the tier still parses and indexes every held text.
- **A model's claims from a promoted passage** (R-296): not built in squiddy.

## Found, and filed where it is fixed

1. **`squiddy init --check` now fails on seldon-biblio** with `declared-but-never-emitted ['Passage', 'PassageOf']`,
   though `squiddy passage promote` writes both. `check()` counts the emitter, the seed, the extraction overlay and
   SQ-101's `derivations.EDGE` as producers, and SQ-151 added two more producers (`passages.py`, and `rows.py` for a
   spec's `rows:`) without adding them. factory-kg shows the same for its four rows-ingested Pattern classes after
   FAC-42. Filed into squiddy as `cc_tasks/2026-11-27_filing_from_seldon_init_check_reports_passage_and_rows_classes_never_emitted.md`
   (task `fb0f9767`, squiddy commit `8d9d5193`). The check is read-only and gates no build; seldon-biblio's `--check`
   reads that one finding until squiddy answers.
2. **SQ-151's base comment drifts every rendered graph's schema** (R-290 says it does not). Already filed by
   aacps-ai-policy and in flight as squiddy SQ-154. seldon-biblio's new epoch carries the banner, as hazbrief-corpus's
   HB-232 epoch does, so SQ-154's fix may move seldon-biblio's schema hash once more; SQ-154 item 4's consumer
   section will name the command.

`seldon cc file` warned that squiddy's event store was dirty before the filing's registration
(`store_dirty_before_registration`): the dirty line was the standing dispatcher's own `dispatch_worktree_named` for a
launch in progress, and the filing's `artifact_created` line joined it. Both are the dispatcher's to reconcile
(AD-038-R1's `record:` commits); this session did not commit in squiddy's primary checkout beside a running dispatch.
