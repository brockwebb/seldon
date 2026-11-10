# SEL-036 RESULT: seldon-biblio is built, released and searched by the prior-art gate; 106 entries, 0 declined, 35 for the Desktop thread; 71 governed Citations resolve to their works

**Task:** `91998dc1`. **Executed:** Claude Code, dispatched, worktree `jaunty-nibbling-brook` (branch
`worktree-jaunty-nibbling-brook`), 2026-11-09 22:55Z to 2026-11-10 01:50Z, on base `7906912`. **Addenda:** none (globbed
`cc_tasks/2026-11-09_SEL-036_*_ADDENDUM*.md` before starting; no file). **Not done, per the launch instructions:**
merge, push, `seldon cc complete`.
**Network:** the task's allowlist only (section C below has the forwarder's log). **Model calls:** zero besides this
session (extraction stays closed).

Recall used: squiddy:2026-11-04_SQ-111_held_bytes_outside_the_checkout_under_a_declared_archive_root_and_an_absent_held_file_refused_design_note_first_RESULT

(SQ-111's archive root is why every held byte lives in `~/kg-archive/seldon-biblio`, outside every checkout, and so
survives this worktree. The other seven hits were not read. Two non-recall precedents shaped the work just as much,
and they are named where they apply: factory FAC-01, the same job for the factory's notes, and aacps AP-02 and
hazbrief HB-01b for touchpoint 3.)

## Premises

| premise | result |
|---|---|
| `test -d governed` | holds |
| `test -f ../squiddy/graphs/biblio/graph.yaml` | holds at the primary. FALSE from this worktree: a dispatched worktree has no siblings (AD-036 ADDENDUM 06), so the relative path misses |
| `test -f ../squiddy/tests/test_sq019_init_inbox.py` | holds at the primary (same caveat) |
| `test -d ../hazbrief-mcp/graphs/hazbrief-corpus/intake/inbox` | holds at the primary (same caveat) |
| `grep -q "graph: ../squiddy/graphs/library" seldon.yaml` | held at base `7906912`. False after this branch, by design: the key is now a two-item list (Part E) |

## Commits (oldest first)

| commit | what |
|---|---|
| `363ca4c` | A: `graphs/seldon-biblio` by `squiddy init` |
| `a435856` | B: seeds, resolver, catalog builder, the checkpoint, the candidates file, the SIGKILL test |
| `ccbbc66`, `1e86370`, `5148d57`, `97095e5`, `0e9d6e8`, `3dd0515` | prior-art searches and dry verifications (the tool commits its own log lines) |
| `f44937d` | E: AD-036 ADDENDUM 12 (R21, R22) and their two register records, BEFORE the code |
| `15caa76` | E: the recorded verdict, AD-036 family PASS |
| `27609ca` | E: the code (multi-graph library arm, the bridge, the domain types, seldon.yaml) and its tests |
| `c6506d6` | E: the bridge run into seldon-seldon-self (events) |
| `b62476d` | the domain tests' type list gains ExternalReference |
| `4082abb` | C, D: first build, release `20261109_sel036` |
| `b587437` | C, D, F: second build, release `20261109_sel036b`, counts, proof |

## Part A: the graph

- `graphs/seldon-biblio/graph.yaml`: biblio's node classes (Work, Standard, Software, Person, Organization, Decision,
  ExternalReference) and the edges the seeded emitter writes; `policy: own_record_or_public`, `visibility: public`;
  the scope in the task's words. `Supersedes` was dropped: `init --check` reported nothing can produce it.
  `squiddy init` through `../squiddy/.venv/bin/squiddy` (seldon.yaml `project_new.squiddy_command`); `init --check`
  clean at every commit since (spec sha256 `d8a1af4e538f` at the end).
- **Where the bytes are.** `archive: {root: ~/kg-archive/seldon-biblio}` (squiddy DN-056 R-246). The task says "where
  hazbrief-corpus stores them per squiddy's config"; hazbrief stores them in its gitignored `texts/` and `corpus/`,
  which a dispatched worktree discards (FAC-01 lost its 31 files that way). The archive root is squiddy's own answer
  to exactly that (SQ-111). Not under `~/Documents`: DN-056 measured 97 % of the files there evicted by iCloud. No
  PDF or HTML is in git; the generated `.gitignore` covers what the layout leaves in the tree.
- The inbox is `intake/inbox/` (R-212), declared in `intake:`.
- The factory control names the task's Network allowlist as `buckets.http` hosts; the allowlisting forwarder refuses
  everything else.

## Part B: the catalog

- **Seeds** (`graphs/seldon-biblio/intake/seeds.yaml`, hand-written from reading each citation): the 72 governed
  Citations deduplicated to **76 entries**, plus **13** from AD-013 ADDENDUM 01 and SEL-035's list only: **89 seeds**.
  Two artifacts' lines name lists (AD-032's audit and decision references: 13 and 12 works). One artifact names no
  work (the AD-030 parser cut it from AD-033-R3's own text). The map from every artifact to its seeds is the file's
  `governed:` block.
- **Resolver** (`scripts/sel036/resolve.py`, config `scripts/sel036/sel036.yaml`): OpenAlex, Crossref, doi.org
  (content negotiation), Semantic Scholar, then the publisher's or project's page (arXiv's export API, PyPI's JSON, the
  GitHub repository, its release and its LICENSE file, or the canonical URL), in that order, the first confirmation
  ending the chain, and every attempt kept with its answer. A software or a standard with no DOI skips the four
  scholarly indexes as `not_applicable` (they index works, not repositories), and the row says so. Checkpointed per
  constitution section 15: one fsynced row per unit, keyed, resume by re-running; progress lines; a pilot; request and
  wall ceilings; failures are rows and are retried once per run. `tests/test_sel036_resolve_checkpoint.py` SIGKILLs
  a run mid-loop and asserts the resumed answer equals an uninterrupted run's and no finished unit's call was repeated.
- **The confirmation rule was amended after the first run's audit** (resolver `sel036-resolve/2`). Title containment
  alone (squiddy's `title_similarity` at the graph's 0.6 floor) matched wrong works on short titles: ArgonDigital to a
  weather-forecasting paper, Krakovna to a JSTOR chapter, Nygard to a Springer chapter, NIOSH to a 2003 nursing
  editorial, Anthropic's post to a Springer chapter, and arXiv:2403.07311 to an ICKG paper. Rev 2: a title search
  must also carry the note's own DOI or arXiv id when the note states one, and share a cited author's surname (record
  linkage on more than one field, Fellegi and Sunter 1969), except a work whose title is token-identical and whose
  year agrees, which is kept with the disagreement recorded. Grey literature gets no exception.
- **Catalog** (`scripts/sel036/build_candidates.py` writes `corpus/candidates/seldon_biblio_candidates.yaml`): 89 seed
  entries plus 17 documentation snapshots = **106 entries**. Each carries kind (and `entry_kind`: work, standard,
  software, grey, documentation), title (the authority's) and `title_cited`, authors, year, venue, publisher, edition,
  DOI / OpenAlex id / arXiv id / ISBN / standard number / repository and version, canonical URL, licence and its URL
  or LICENSE file line, `cited_in`, `governed_citations`, `resolved_by`, every attempt, and posture fields.
  A paywalled standard (ISO, IEEE, SAE, RTCA, PMI) is `access: purchase`, metadata only, never declined.
- **Resolved by:** OpenAlex 51, Crossref 3, Semantic Scholar 1, the publisher's page 16, none 18 (standards and grey
  items no authority could be asked about, all metadata-only or manual, none declined).
- **Where the notes are wrong**, found by resolution and recorded on each entry (`citation_discrepancies`), for the
  operator to correct or erratum:
  - `seldon_architectural_decisions.md` cites Saga as doi `10.1145/3514221.3526052`; the work is `...3526049`
    (arXiv's own record for 2204.07309).
  - `cc5_sleep_function_architecture.md`: "Adler et al. (2021)" is Saeedi, Peukert and Rahm, ESWC 2020; "Xiang et al.
    (2025)" SplitE is Wang et al.; "Li et al. (2024)" KG-LLM is Shu et al.; "Ebraheem et al. 2016/2021" for
    arXiv:2104.03986 is Jain, Sarawagi and Sen (PVLDB 2021).
  - Several notes cite a preprint whose published version is now the record (ExpeL, Self-Route, arXiv:2406.14325,
    Chen et al., Saga); kept, both identifiers held.

## Part C: acquisition

- **Documentation snapshots** (my fetcher, the same checkpoint): 17 pages and READMEs at the hosts SEL-035 and the
  task name, plus the three OMG specifications (omg.org is allowlisted and the specs are free): 17 of 17 fetched, raw
  bytes under `docs/raw/`, a form-feed `.txt` derivative under `docs/text/` (a PDF is its own text), sha256, URL and
  retrieval time on each entry. One path had moved: OpenFastTrace's `doc/user_guide.md` is now
  `doc/user_guide/user_guide.md` (recorded on the seed as `texts_moved`); the held page is that guide's index, whose
  body is split into child pages that were not fetched.
- **Works' open texts** came through squiddy's own acquire stage (the graph's acquisition path), behind the allowlisting
  forwarder: 16 open-access PDFs held (arXiv and the OA versions OpenAlex lists).
- **The forwarder's log** (`factory/egress.jsonl`): requests reached only `api.crossref.org`, `api.openalex.org`,
  `doi.org`, `arxiv.org`, `dl.acm.org`, `www.iso.org` and `www.omg.org`. 30 other hosts were refused and logged, never
  contacted, including `api.github.com` (squiddy's software resolver; the catalog carries what github.com's pages and
  PyPI say instead) and `api.datacite.org` (an arXiv DOI's agency).
- **No contact address went anywhere**: the user agent is `seldon-biblio/0.1 (SEL-036; ...)` and squiddy's renders
  none (FAC-01's finding).
- **This session has no browser tool**, so every refused or off-allowlist text is marked for the Desktop thread (the
  table at the end).
- **Not done:** my fetcher did not read robots.txt before its 17 page fetches (squiddy's acquire does, DN-055 R-241).
  All 17 are documentation and README pages on hosts that publish them for reading.

## Part D: admitted

Two builds (`squiddy build`, extraction closed), both rc 0 with every release gate passing (export, conform, dangling,
conformance, presence, halts, text_held, anchors, index, index-parity, claims-reachable, host-posture, diff,
registers, seal) and the serve check answering. Release **`20261109_sel036b`** is served.

| count | n |
|---|---|
| cataloged | 106 |
| resolved by an authority (or fetched, for a snapshot) | 87 |
| acquired with text | 33 |
| metadata-only | 73 (21 no OA text exists, 14 standards with no DOI, 13 OA text on a host this task could not use, 10 software, 7 grey whose page is off the Network line, 5 purchase, 3 OA without a PDF location) |
| marked for manual acquisition | 35 (table at the end) |
| declined | 0 |
| admitted (in graph) | 106 |

Evidence: `graphs/seldon-biblio/evidence/sel036/part_d_counts.json`, `evidence/20261109_sel036*/`.

**What went wrong on the way, and what changed:**
1. The first build stopped at the kit's 25 GB disk floor (21.96 GB free). This graph holds 11 MB, so the spec now
   declares `disk: {floor_gb: 10}` with that basis on its face.
2. Touchpoint 3 (DN-027 R-127) stopped both builds. I answered it in `factory/control.yaml` on the operator's
   recorded order, as aacps AP-02 and hazbrief HB-01b did (106 entries, then 14), with the basis written beside it.
   The operator overrides by editing a seed and re-running.
3. The first build quarantined all 12 HTML/README snapshots. I had written their derivatives as `.md`, and squiddy's
   acquire reads only PDF and form-feed `.txt` (squiddy `docs/KIT_BOUNDARY.md`, which I should have read first). The
   fetcher now writes `.txt` (`sel036-fetch/2`).
4. `li2024kgllm` halted: its arXiv DOI is answered only by DataCite, which the Network line does not name, and
   OpenAlex has no record. The catalog now keeps that DOI as `arxiv_doi` and takes the text from arxiv.org.
5. **My error, caught before it landed:** the first attempt at build 2 opened revisions (squiddy R-213) for 70
   unchanged entries, because I had declared `sha256`, `acquisition` and `openalex_id` as content fields, and squiddy's
   acquire writes all three into the manifest. Its catalog writes were reverted (my own uncommitted files) before
   assess, and the content fields are now only fields the candidate alone writes
   (`doi, arxiv_id, access, raw_sha256, text_sha256`). A read-only prediction with squiddy's own `content_of` showed
   0 revisions and 14 refreshes before the re-run, which is what happened.
6. Parse took 87 minutes. docling spent 45 minutes on the SysML v2 specification PDF and 17 on KerML. The kit caps
   each text at 3,600 s; neither hit the cap.

## Part E: the bridges, and AD-036 ADDENDUM 12

- **R21: the library arm searches a list.** `prior_art.library.graph` takes a list, and seldon.yaml names
  `../squiddy/graphs/library` and then `graphs/seldon-biblio`. Each graph is searched and receipted on its own: a
  receipt names one release, so rows are never merged across graphs. Reciprocal Rank Fusion, the merge the library
  holds a system using, was considered and declined for that reason.
  A receipt names its graph (`| graph <name> |`). One that names none is verified in the first graph, so every
  receipt written before R21 verifies unchanged. A graph with no served release is reported unavailable beside the
  others and fails no search.
- **R22: the bridge.** Each governed Citation `resolves_to` an `ExternalReference` named `seldon-biblio:<entry id>`, a
  pointer carrying the entry's identifier and title and nothing of its content (squiddy biblio's class, DI-046; OD-4
  section 3.3).
  - **Domain-config additions, with the reason.** `ExternalReference` and `resolves_to` are ADDED to
    `seldon/domain/research.yaml`. No existing relationship has `Citation` as its source, and none reaches outside the
    graph.
  - **Run:** 71 Citations mapped, **76 pointers, 110 links**, 0 Citations or entries missing. The one Citation left
    unlinked names no work. `works_for_ruling` now answers, for example, AD-029:
    `doi:10.1145/368996.369025` (Kahn 1962), `doi:10.1145/1460299.1460318` (Kelley and Walker 1959) and
    `standard:ANSI/PMI 99-001`. Evidence: `evidence/sel036/bridge.json` and `works_for_ruling.json`.
- **Rule order held:** the addendum, its receipts (1 library, 3 internal) and its register records were committed
  (`f44937d`), and `prior-art verify` on the AD-036 family passed and was recorded (`15caa76`: 45 pass, 12 pass
  superseded, 1 self-citation), before the code commit (`27609ca`).
- **Numbering:** I first wrote R20 and R21. `decision accept` refused R20, because ADDENDUM 11 already holds it. The
  rulings are R21 and R22.
- **The addendum carries no `graph seldon-biblio` receipt, on purpose.** That graph's index is gitignored, so on the
  primary such a receipt fails `release_unavailable` until the primary holds a release (section 4 of the addendum).
  A FAIL verdict on AD-036 would hold every task it governs.
- **Tests:** `tests/test_sel036_library_graphs.py` (10) and `tests/test_sel036_biblio_bridge.py` (4, on the live
  test database). The code came before these tests here, against the TDD rule; both files fail on base code, which
  has no `Libraries` and no `biblio_bridge`.
- **One existing seam kept:** `tests/test_cc_register_commits_note.py` replaces `pa.Library` with a one-argument stub,
  so `Libraries` builds the first graph as `Library(s)`, exactly as every caller before R21 did.

## Part F: the proof

`scripts/sel036/proof.py` ran AD-013 ADDENDUM 01's two library queries and the task's three against both graphs. The
second graph was this worktree's release; the primary has none until the recipe below. Output is in
`evidence/sel036/proof.json`.

| query | squiddy library (top documents) | seldon-biblio (top documents) |
|---|---|---|
| requirements traceability matrix | model-training preprints (arXiv 2603.28589, 2607.02771, ...) | ArgonDigital verification methods, Gotel and Finkelstein 1994, Cleland-Huang 2012, ReqIF 1.2, Requiem, NASA SWE-072, Cleland-Huang 2014, Doorstop |
| trace link maintenance | model-training preprints | Agent-as-a-Judge (noise), Requiem, Cleland-Huang 2014, OpenFastTrace README, sphinx-needs dynamic functions, LiSSA, SysML v2, Antoniol 2002 |
| suspect link | model-training preprints | **Requiem** first, then Saga (noise), KerML, KG-LLM (noise), sphinx-needs, Doorstop README |
| generated region markers | model-training preprints | **Cog `running.html`** first, then noise (SkillNet, KerML, ...) |
| verification method inspection analysis demonstration test | model-training preprints | **ArgonDigital** (page and record), SysML v2, **Scukanec and van Gaasbeek 2010**, SAE AS9102B, then noise |

So rows from seldon-biblio now answer all five queries with the works AD-013 ADDENDUM 01 had to cite by name.
squiddy's library still answers none of them. The lower ranks of a 106-entry corpus carry noise.

## Tests

- The full suite on this branch (`-n 6`, while docling ran): **3,334 passed, 5 failed, 7 skipped, 41 min.**
- Two failures were mine: `test_docs::test_artifact_types_has_all_types` and `test_domain::test_load_domain_config`
  pin the domain's type list. They now include ExternalReference (`b62476d`) and pass.
- The other three are known and unrelated:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: library index
    drift, failing on main.
  - `test_dispatch_parallel::test_two_disjoint...`: passed alone.
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...`: failed alone too, under
    docling's load. It touches no file this task changed, and it fails identically on main's code under load
    (SEL-029 RESULT).
- Every prior-art test family (`test_prior_art*`, `test_sel029_*`, `test_disp003`, `test_desk002`,
  `test_cc_register_commits_note`, `test_hooks`) passed after the seam fix.

## After the merge: give the primary its served release (operator or Desktop, one shell, in this order)

The served export, the index and the parse intermediates are gitignored, so the merge brings the graph's record and
not its release. Until step 1 runs, `seldon prior-art search --library` reports `graph seldon-biblio: unavailable` and
fails nothing. The outputs are staged outside every repository, so no re-parse (87 minutes) is needed.

1. `cp -R ~/kg-archive/seldon-biblio/build_outputs/20261109_sel036b/. /Users/brock/GitHub/seldon/graphs/seldon-biblio/`
2. `cd /Users/brock/GitHub/seldon && /Users/brock/GitHub/squiddy/.venv/bin/squiddy init graphs/seldon-biblio --check && git status --short graphs/`
   (expect a clean check and no output from status: everything copied is ignored)
3. `cd /Users/brock/GitHub/seldon && python -m dotenv -f .env run -- /Users/brock/GitHub/squiddy/.venv/bin/python scripts/sel036/proof.py --biblio graphs/seldon-biblio --out /tmp/sel036_proof_primary.json`
   (expect five `[seldon-biblio]` lines naming works, as in Part F)

A later task that rebuilds this graph in a worktree should add these to `dispatch.worktree_links`:
`graphs/seldon-biblio/work`, `graphs/seldon-biblio/exports` and `graphs/seldon-biblio/corpus/parsed`. I did not
add them, because the links would name primary directories that do not exist before step 1.

## For the Desktop thread: the 35 entries marked for manual acquisition

Fetch each one with the operator's browser into `graphs/seldon-biblio/intake/inbox/` in the primary checkout, then fill
its stub (`inbox_source_url`, `inbox_obtained_from`, `inbox_licence`, `inbox_stated_by`). The route was validated on
2026-10-23.

Off-allowlist means the host is outside this task's Network line. It was never asked, so it is no evidence of a bot
wall.

**Hosts that refused a scripted request (posture `refused`, HTTP 403 from the forwarder's allowed path):**

| entry | url |
|---|---|
| kahn1962topological | https://dl.acm.org/doi/pdf/10.1145/368996.369025 |
| kelley1959critical | https://dl.acm.org/doi/pdf/10.1145/1460299.1460318 |
| erman1980hearsay | https://dl.acm.org/doi/pdf/10.1145/356810.356816 |
| xiang2025splite | https://dl.acm.org/doi/pdf/10.1145/3768620 |

**Open texts on hosts off this task's Network line:**

| entry | url |
|---|---|
| gotel1994traceability | https://discovery.ucl.ac.uk/749/1/2.2_rtprob.pdf |
| clelandhuang2012traceability | http://www.gbv.de/dms/ilmenau/toc/673088804.PDF (a table of contents only; the book is Springer's) |
| browning2014doorstop | https://content.scirp.org/pdf/jsea_2014032713545074.pdf |
| mayer2009multimedia | https://www.jstage.jst.go.jp/article/arepj1962/41/0/41_27/_pdf (OpenAlex's OA location; check it is the book) |
| groth2010nanopublication | https://content.iospress.com/download/information-services-and-use/isu613 |
| shotton2010cito | https://jbiomedsem.biomedcentral.com/track/pdf/10.1186/2041-1480-1-S1-S6 |
| fuchss2025lissa | https://publikationen.bibliothek.kit.edu/1000178348/156555617 |
| rethlefsen2021prismas | https://systematicreviewsjournal.biomedcentral.com/track/pdf/10.1186/s13643-020-01542-z |
| pershina2014graph | pqdtopen.proquest.com (thesis; OpenAlex W2566161782) |
| han2017checklists | https://doi.org/10.1371/journal.pone.0183591 (PLoS ONE, CC BY) |
| aaai_v40i44_41105 | https://doi.org/10.1609/aaai.v40i44.41105 |
| adler2021incremental | https://www.ncbi.nlm.nih.gov/pmc/articles/7250616 |
| doc_ibm_doors_1 | https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors |
| krakovna2020specgaming | https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/ |
| nist_sp800_53r5 | https://doi.org/10.6028/NIST.SP.800-53r5 (nvlpubs.nist.gov) |
| cfr21_11_10e | https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11/subpart-B/section-11.10 |
| w3c_prov_o | https://www.w3.org/TR/prov-o/ |
| slsa_v1_0 | https://slsa.dev/spec/v1.0/ |
| rfc9162 | https://www.rfc-editor.org/rfc/rfc9162 |
| rfc8493 | https://www.rfc-editor.org/rfc/rfc8493 |
| premis_3_0 | https://www.loc.gov/standards/premis/v3/ |
| oais_iso14721 | https://public.ccsds.org/Pubs/650x0m2.pdf (CCSDS 650.0-M-2, free; identical to ISO 14721:2012) |
| gao_02_195 | https://www.gao.gov/products/gao-02-195 |
| nasa_oig_ig_12_012 | https://oig.nasa.gov/docs/IG-12-012.pdf |
| nygard2011adr | https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions |
| niosh_hierarchy_of_controls | https://www.cdc.gov/niosh/hierarchy-of-controls/ |
| randomlabs2026slate | https://randomlabs.ai/blog/slate |

**No URL known to the note (find, then fetch):**

| entry | what to find |
|---|---|
| who_trs1033_annex4 | WHO Technical Report Series 1033, Annex 4, "Guideline on data integrity" (2021) |
| ndsa_levels_v2 | NDSA Levels of Digital Preservation v2.0 (2019) |
| nasa_swe_072 | NASA NPR 7150.2 (SWE-072, bidirectional traceability) |
| anthropic2026seeing | Anthropic, "Lessons from Building Claude Code: Seeing Like an Agent" (2026), on anthropic.com |

## Usage

- **Tokens:** 519,012 at the Parts C to E boundary (`seldon dispatch part-complete`), against an estimate of 1.3M and
  a stop at 1.6M. Part F is recorded after this file's commit.
- **Wall:** about 2 h 55 min. 87 minutes of it was docling parsing the OMG specifications, and 41 the full suite.
- **Network:** the resolver made 180 requests on rev 2 plus 16 refetches, the first run made 145, and squiddy's
  acquire made 151 allowed requests.
- **Model calls:** none outside this session.
- **The resolver's pilot projection was meaningless.** Its first six units were `not_applicable` rows that make no
  request, so it projected 6 s for a run that took 4 minutes. It is reported here, not fixed: a pilot over
  no-request units should be skipped, which is a one-line change for the next task that touches the resolver.
