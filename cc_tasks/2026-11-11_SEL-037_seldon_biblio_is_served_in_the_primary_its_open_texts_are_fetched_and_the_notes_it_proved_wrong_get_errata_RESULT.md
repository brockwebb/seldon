# SEL-037 RESULT: release 20261111_sel037 is installed in the primary (it answers once this branch merges); 18 of 31 open texts fetched after robots.txt; 17 left manual; two errata

**Task:** `0e49ea54`. **Executed:** Claude Code, dispatched, worktree `curried-mixing-bubble` (branch
`worktree-curried-mixing-bubble`), 2026-11-12 02:35Z to about 05:00Z, on base `190bd0c`. **Addenda:** none (globbed
`cc_tasks/2026-11-11_SEL-037_*_ADDENDUM*.md` before starting; no file). **Not done, per the launch instructions:**
merge, push, `seldon cc complete`.
**Network:** the task's allowlist only (scripts/sel037/sel037.yaml `allowlist`, checked on every redirect hop).
dl.acm.org was not asked. **Model calls:** none outside this session; extraction stayed closed.

Recall used: seldon:2026-11-09_SEL-036_seldon_gets_a_bibliographic_graph_every_cited_source_is_a_resolved_work_with_its_metadata_and_text_RESULT

(It is this task's named input. Its last three sections are the install recipe, the 35 manual entries and the
staged-outputs path, and its Part D list of build traps decided how the rebuild was run. The other seven hits were
not read.)

## Premises

| premise | result |
|---|---|
| `test -f graphs/seldon-biblio/graph.yaml` | holds |
| `test -f graphs/seldon-biblio/intake/inbox/.gitkeep` | holds |
| `! test -f graphs/seldon-biblio/exports/seldon_biblio_graph.json` | held in this worktree, and in the primary until Part A |

## Commits (oldest first)

| commit | what |
|---|---|
| `120d23e` | A: why `worktree_links` cannot carry a release (seldon.yaml comment and its test) |
| `f476d24` | B: the fetcher, its overlay on SEL-036's catalog, the checkpoint, the catalog rebuilt, the SIGKILL test |
| `dd6b6f0` | D: the two errata |
| `659b16e` | C: release `20261111_sel037`, built, its record, and the stage-and-install script |
| `871fdba` | C: the proof and the counts |
| `fdec6a3`, `e4c36c5`, ... | the gate's own log lines for every `prior-art search` it ran (AD-036-R11) |

## Part A: the release where the gate reads it

**Installed.** Release `20261109_sel036b` was copied from `~/kg-archive/seldon-biblio/build_outputs/20261109_sel036b/`
into the primary. All 265 copied files are gitignored (`git check-ignore --no-index`: 265 of 265), so the primary's
`git status` is unchanged. `squiddy init graphs/seldon-biblio --check` in the primary: clean (spec `bf00d480f564`).
`seldon prior-art search "suspect link" --library` then answered with `graph seldon-biblio: release
seldon_biblio_graph_20261109_sel036b_2026-11-09.json ..., 39 row(s)`. Requiem ranked first.

That was replaced in Part C by `20261111_sel037`; see "The primary until the merge" below.

**`dispatch.worktree_links`: cannot carry this, so the Part stopped there and declares no link.** The reasons:

1. `graphs/seldon-biblio/exports` holds five tracked files (EXPORT_VERSIONS.md and the diff and host-posture
   reports), so every worktree checkout creates the directory. `worktree.link` skips a destination that exists
   (`seldon/core/worktree.py` `link`). Declaring the directory is a silent no-op.
2. hazbrief (HB-73 Part A) and aacps link the served export **file** instead. I adopted that as prior art and then
   checked it against seldon's receipts. squiddy publishes the served copy with `shutil.copyfile(versioned, latest)`,
   which writes through a link, so the primary's served file and its index would update. But a library receipt names
   the **versioned** export (`release seldon_biblio_graph_<label>_<date>.json`). Verification looks for that file in
   the primary's `exports/` (`Library.export_path`; receipts verify at the primary through `corpus_anchor`). The file
   gets a new name every release, so no link declared in advance can name it, and it would be deleted with the
   worktree. With `work` and the served file linked, the primary would serve a release whose receipts fail
   `release_unavailable`. That holds every task the citing note governs.

`tests/test_sel037_worktree_links_exports.py` pins both facts: the directory is never linked, and with the
file-and-work links a worktree build updates the primary's served file and index but not the versioned export. The
reason is written at `seldon.yaml` `dispatch`, where `worktree_links` would go. No second mechanism was invented. A
release built in a worktree is installed by copying its ignored outputs, the route SEL-036 staged. It is now a script,
`scripts/sel037/stage_release.sh <label> <primary>`: it stages the outputs under the archive root, copies them in, and
deletes nothing.

The gate needs no link to read the release. From any worktree, `prior_art.corpus_anchor` resolves
`graphs/seldon-biblio` to the primary's directory. The proof records that path.

## Part B: fetch

**The fetcher:** `scripts/sel037/fetch.py`, every target and tunable in `scripts/sel037/sel037.yaml`. It reuses
SEL-036's allowlisted client, snapshot writer and posture vocabulary (imported), and squiddy's own RFC 9309 robots
reader (`squiddy.posture.Observer`, DN-055 R-241). **robots.txt is read for every origin before any document or
discovery page there is requested**, which is the step SEL-036's fetcher skipped. Raw bytes and the form-feed `.txt`
derivative go under the archive root (`docs/raw`, `docs/text`). Each text is checked with squiddy's reader
(`acquire.text_chars`): it must clear the floor (1,200 characters for a PDF, 400 for a page), carry an `expect`
pattern, and where declared have a minimum page count. A text that fails is `rejected` and never kept.
Checkpointed per section 15: one fsynced row per target, keyed by the target's whole spec, resume by re-running,
pilot, progress, ceilings (600 requests, 3,600 s). `tests/test_sel037_fetch_checkpoint.py` SIGKILLs a run mid-loop,
resumes it, and asserts the uninterrupted outcome with no finished unit asked twice. Three more tests cover the
overlay.

**Into the catalog:** `scripts/sel037/overlay.py`, applied by SEL-036's builder through a new config key
(`scripts/sel036/sel036.yaml` `acquired_overlays`). `build_candidates.py --check` matches.
- A held work's text goes on its entry. `raw_sha256` (a declared content field) moves, so an entry admitted
  metadata-only is re-admitted as a **revision** (squiddy SQ-023 R-213). That is the kit's own route for "bytes
  supplied later".
- A standard's text becomes a documentation entry `doc_<standard>_1` that documents it, as SEL-036 held the OMG
  specs, because squiddy's acquire gives a `standard` no text. The standard names it (`text_in`).
- Every held entry carries the filled stub: `inbox_source_url`, `inbox_obtained_from`, `inbox_licence`,
  `inbox_stated_by`. The last gives the licence's basis and every Creative Commons licence URL found in the text.
- A predicted-revision check (catalog before and after) showed only the 31 targeted entries changed. Content fields
  moved on exactly the 9 works whose text is now held.

**Outcome of the 31 (27 off the old Network line, plus 4 with no URL):** 18 fetched, 13 not.

| fetched | what is held |
|---|---|
| gotel1994traceability, browning2014doorstop (CC BY 4.0 in its text), fuchss2025lissa, han2017checklists (CC BY 4.0), aaai_v40i44_41105, krakovna2020specgaming, nasa_oig_ig_12_012, nygard2011adr, niosh_hierarchy_of_controls | the text on the entry (9 revisions) |
| nist_sp800_53r5, who_trs1033_annex4, w3c_prov_o, slsa_v1_0, rfc9162, rfc8493, premis_3_0, nasa_swe_072 | `doc_<id>_1` (8 new entries) |
| OpenFastTrace's user guide | 34 child pages, `doc_sw_openfasttrace_ug_<section>_<page>` (SEL-036 held only the index) |

**How the 4 without a URL were found:**
- WHO TRS 1033: the IRIS record of the whole report (Annex 4 is inside it). The first bitstream that carries "data
  integrity" was taken.
- NPR 7150.2: 7150.2D from NODIS.
- NDSA Levels v2.0: the NDSA page, which redirects off the Network line (below).
- Anthropic's post: a web search. It is at `claude.com/blog/seeing-like-an-agent`, not on www.anthropic.com, and
  claude.com is not on the Network line.

**The two checks the task named:**
- **`mayer2009multimedia`: not the book, not kept.** J-STAGE's robots.txt disallows the `_pdf` path, so the landing
  page was fetched instead. It is Mayer, R. E. (2002), "Multimedia Learning", *The Annual Report of Educational
  Psychology in Japan* 41:27-29, doi 10.5926/arepj1962.41.0_27, three pages. OpenAlex's only OA location for the 2009
  book is a different work. The book (Cambridge) has no free copy, so the entry is metadata-only with that finding
  (`no_open_access_text`) and is **not** on the manual list. A browser pass would find nothing to fetch.
- **`clelandhuang2012traceability`:** the URL is GBV's table-of-contents scan, labelled so on the entry
  (`sel037_label`). www.gbv.de is not on the Network line, so it was not fetched. It stays manual, labelled as a
  table of contents only.

**One more finding: NPR 7150.2D has no SWE-072.** Bi-directional traceability is its section 3.12.1, `[SWE-052]`. The
requirement numbers jump from SWE-071 to SWE-073. The number the citing note uses comes from an earlier revision,
which NODIS no longer serves (`N_PR_7150_002C_` answered 404). 7150.2D is held as the current text, and the finding
is on the entry (`sel037_note`). The note citing SWE-072 is not in condition 3, so no erratum was written. It is
listed for the Desktop thread below.

**Robots reads that redirected off the Network line** are recorded as this task's refusal, naming the hop. They are
never recorded as a robots rule the host did not state (fetcher version 2). Those hops were link.springer.com for both
BMC journals, www.doi.org, ccsds.org, www.ndsa.org and unblock.federalregister.gov (the eCFR's bot page).

## Part C: rebuild and prove

**Build** `squiddy build --graph graphs/seldon-biblio --version 20261111_sel037`, extraction closed: **rc 0, 5,834 s**.
- Touchpoint 3 stopped the first attempt at 51 undecided. That is exactly 42 new text entries plus 9 revisions. It was
  answered in `factory/control.yaml` on SEL-036's recorded basis, with the local date (EST).
- Acquire took the held texts for 51 of 51.
- Parse: **83 of 84 texts**. `doc_nist_sp800_53r5_1`'s parse child **died by SIGSEGV after 3,017 s**. It was the
  first of the 492-page PDFs, and it ran while this session's test runs loaded the machine. squiddy holds it out of
  the index with its reason (`parse_refused`, SQ-103). It keeps one retry, so the next build of this graph asks again
  (`attempts_before_held: 2`). I did not spend a second ~50-minute build on that retry here. The PDF is held under the
  archive root.
- **Every release gate passed:** export, conform, dangling, conformance, presence, halts, text_held, anchors-by-id,
  index, index-parity, anchors, claims-reachable, host-posture, diff, registers, seal. The serve check answered.
  Evidence: `graphs/seldon-biblio/evidence/20261111_sel037/`.

**Installed in the primary** with `scripts/sel037/stage_release.sh 20261111_sel037 /Users/brock/GitHub/seldon`.
- It staged the outputs at `~/kg-archive/seldon-biblio/build_outputs/20261111_sel037/` and copied them in: 421 files,
  all gitignored (421 of 421).
- `init --check` is clean. The primary's index names `exports/seldon_biblio_graph_20261111_sel037_2026-11-11.json`
  (sha256 `076422bb8382...`).

**The primary until the merge.** The library arm cuts receipt rows using the graph's tracked `corpus/manifest.yaml`.
Until the dispatcher merges this branch, the primary holds the new index beside SEL-036's manifest, so the arm reports
`graph seldon-biblio: release_unavailable ... gotel1994traceability holds no text (local_path)`. Under R21 that fails
no search. It is recorded in `evidence/sel037/proof_primary_before_merge.json`. I did not copy tracked files into the
primary: that would dirty its tree and block every dispatch (c7). The merge brings the manifest, and nothing else is
needed. No step is handed to anyone.

**The proof, in the post-merge state, through the gate's own command.** `scripts/sel037/proof.py --project <dir>` runs
`seldon prior-art search "<q>" --library --json` five times. `<dir>` was a scratch directory holding exactly the
post-merge files: `git archive HEAD` of `seldon.yaml` and `graphs/seldon-biblio`, plus the staged outputs byte for
byte as installed. Output: `evidence/sel037/proof.json`.

| query (SEL-036 Part F) | seldon-biblio rows | top documents |
|---|---|---|
| requirements traceability matrix | 33 | Gotel and Finkelstein 1994, OpenFastTrace guide (broken requirement branches), NPR 7150.2D, ArgonDigital, LiSSA, Requiem, Cleland-Huang 2012, ReqIF |
| trace link maintenance | 35 | LiSSA, OpenFastTrace guide (API, command line), Requiem, Agent-as-a-Judge, OpenFastTrace (partial tracing), Doorstop paper, WHO TRS 1033 |
| suspect link | 38 | Requiem, Saga, KerML, KG-LLM, sphinx-needs, Doorstop README, LiSSA, PROV-O |
| generated region markers | 50 | Cog `running.html`, PROV-O, then noise |
| verification method inspection analysis demonstration test | 42 | ArgonDigital, SysML v2, WHO TRS 1033, Scukanec and van Gaasbeek 2010, NPR 7150.2D |

All five return `graph seldon-biblio` rows from `20261111_sel037`, and the texts Part B fetched now rank. The squiddy
library answered beside it as before.

**Counts** (`scripts/sel037/counts.py`, `evidence/sel037/part_c_counts.json`):

| count | SEL-036 | SEL-037 |
|---|---|---|
| cataloged | 106 | 148 (+8 standards' texts, +34 OpenFastTrace pages) |
| acquired with text | 33 | 84 (83 indexed; NIST SP 800-53 held, parse refused) |
| metadata-only | 73 | 64 |
| marked for manual acquisition | 35 | 17 |
| declined | 0 | 0 |

**A record gap, stated rather than patched:**
- Eight standards whose text is now held in `doc_<id>_1`, and the manual entries whose posture SEL-037 re-observed,
  still carry SEL-036's `manual_acquisition` and posture in the manifest. squiddy does not refresh an in-graph entry
  from its catalog row outside a declared content field ("a correction to released metadata is a new revision"), and
  inventing a content-field change to force one would be the kludge.
- The catalog is the record for those fields. `counts.py` takes the catalog's word and says so in its docstring.
- The release's own host-posture report therefore still lists them as SEL-036 saw them.

## The manual list, for the Desktop thread's one browser pass

Fetch each one into `graphs/seldon-biblio/intake/inbox/` in the primary and fill its stub (`inbox_source_url`,
`inbox_obtained_from`, `inbox_licence`, `inbox_stated_by`). Status, first bytes and time for each are on its catalog
entry (`posture_evidence`, `posture_observed_at`) and in `evidence/sel037/units.jsonl`. "Off the Network line" means
this task could not ask that host, so it is no evidence of a bot wall.

| entry | url | posture (SEL-037, 2026-11-12) |
|---|---|---|
| kahn1962topological | https://dl.acm.org/doi/pdf/10.1145/368996.369025 | refused (HTTP 403, SEL-036; not retried, per the task) |
| kelley1959critical | https://dl.acm.org/doi/pdf/10.1145/1460299.1460318 | refused (HTTP 403, SEL-036; not retried) |
| erman1980hearsay | https://dl.acm.org/doi/pdf/10.1145/356810.356816 | refused (HTTP 403, SEL-036; not retried) |
| xiang2025splite | https://dl.acm.org/doi/pdf/10.1145/3768620 | refused (HTTP 403, SEL-036; not retried) |
| groth2010nanopublication | https://content.iospress.com/download/information-services-and-use/isu613 | bot wall: HTTP 403 "Just a moment..." (Cloudflare challenge); robots allow |
| gao_02_195 | https://www.gao.gov/assets/gao-02-195.pdf | bot wall: HTTP 403 "Access Denied" (product page too); robots allow |
| adler2021incremental | https://pmc.ncbi.nlm.nih.gov/articles/PMC7250616/ | bot wall: HTTP 403 "403 Forbidden"; robots allow |
| doc_ibm_doors_1 | https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors | JavaScript shell (HTTP 200, no text) |
| randomlabs2026slate | https://randomlabs.ai/blog/slate | JavaScript shell (HTTP 200, no text) |
| pershina2014graph | http://pqdtopen.proquest.com/#viewpdf?dispub=10139524 | robots.txt answered HTTP 521 (origin down), read as disallow-all (RFC 9309 2.3.1.4) |
| cfr21_11_10e | https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11/subpart-B/section-11.10 | redirected to unblock.federalregister.gov (eCFR's bot page); the API path is disallowed by robots.txt |
| shotton2010cito | https://jbiomedsem.biomedcentral.com/track/pdf/10.1186/2041-1480-1-S1-S6 | robots.txt redirects to link.springer.com, off the Network line |
| rethlefsen2021prismas | https://systematicreviewsjournal.biomedcentral.com/track/pdf/10.1186/s13643-020-01542-z | robots.txt redirects to link.springer.com, off the Network line |
| oais_iso14721 | https://public.ccsds.org/Pubs/650x0m2.pdf | robots.txt redirects to ccsds.org, off the Network line |
| ndsa_levels_v2 | https://ndsa.org/publications/levels-of-digital-preservation/ (the v2.0 document is on OSF) | robots.txt redirects to www.ndsa.org, off the Network line |
| anthropic2026seeing | https://claude.com/blog/seeing-like-an-agent | claude.com is off the Network line (found by web search) |
| clelandhuang2012traceability | http://www.gbv.de/dms/ilmenau/toc/673088804.PDF | **a table of contents only** (the book is Springer's); www.gbv.de is off the Network line |

**Also for the Desktop thread:** the note that cites "NPR 7150.2 SWE-072" cites a requirement number that 7150.2D
does not carry (it is SWE-052, section 3.12.1). Whether that warrants an erratum is the Desktop thread's call.

## Part D: errata

- `docs/design/seldon_architectural_decisions_erratum_01_saga_doi.md`. The note's DOI `10.1145/3514221.3526052`
  resolves at Crossref to a different SIGMOD 2022 paper, "Deploying a Steered Query Optimizer in Production at
  Microsoft". Saga is `10.1145/3514221.3526049` (Crossref, and arXiv's record of 2204.07309). Preprint and published
  version are both named. Entry `ilyas2022saga`.
- `docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture_erratum_01_misattributed_authors.md`. It covers
  four rows:
  - "Adler et al. (2021)" is Saeedi, Peukert and Rahm, ESWC 2020 (LNCS), doi 10.1007/978-3-030-49461-2_23, checked at
    Crossref.
  - "Li et al. (2024)" KG-LLM is Shu et al., arXiv:2403.07311.
  - "Xiang et al. (2025)" SplitE is Wang et al., doi 10.1145/3768620.
  - "Ebraheem et al." is Jain, Sarawagi and Sen, PVLDB 15(1), doi 10.14778/3485450.3485455; the volume was checked at
    Crossref, and the preprint arXiv:2104.03986 is named.

Each row quotes the note's own string and gives the work, its identifier and its seldon-biblio entry id. The notes are
not edited. Both files match the gate's `*_erratum_*.md` exemption. Neither base note carries an `AD-`/`DN-` id, so
`governing_commit._base_of` attaches neither to a base note, which is as before for these two notes.

## Tests

- New: `tests/test_sel037_worktree_links_exports.py` (2) and `tests/test_sel037_fetch_checkpoint.py` (4: the SIGKILL
  resume and three overlay cases). They pass under the project interpreter and squiddy's.
- Run while the build parsed: the SEL-036 and SEL-037 families, `test_sel017_links_hook_parts`,
  `test_dispatch_parallel_held` (37 passed), and `test_prior_art*`, `test_cc_register_commits_note` and
  `test_dispatch` (158 passed).
- **The full suite** on this branch (`-n 6`, `PYTHONPATH` = this worktree, dotenv): **3,371 passed, 3 failed,
  7 skipped, 39 min.** None of the three touches a file this task changed:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: squiddy library
    index drift, failing on main (SEL-036 RESULT).
  - `test_friction002_auto_mode::test_a_classifier_breaker_becomes_a_line_stop_with_the_classifiers_reason`: passed
    alone (29 passed with the next file's 13).
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...`: fails alone too, identically
    on main's code (SEL-029 and SEL-036 RESULTs).

## Usage

- **Tokens:** 322,220 at the Parts C and D boundary (`seldon dispatch part-complete`), against an estimate of 0.7M and
  a stop at 0.85M.
- **Wall:** about 2 h 25 min. The build took 97 minutes of it, of which NIST's crashed parse took 50.
- **Network:** the fetcher made 169 requests over five runs (`evidence/sel037/progress.txt`: the v1 pilot 7, v1 56,
  v2 102, and the two Mayer re-checks 2 each). Probes for
  discovery and the errata made about 20 more, all to allowlisted hosts. squiddy's acquire asked only api.crossref.org
  and api.openalex.org (5 each).
- **Model calls:** none outside this session.
- **Disk:** 14 GB free at the start against the graph's 10 GB floor.
