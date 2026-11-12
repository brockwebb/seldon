# SEL-037: seldon-biblio is served in the primary checkout, the open texts SEL-036 could not reach are fetched and admitted, and the notes it proved wrong get errata

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-11, from the OODA on SEL-036 and SEL-035.
**Repo:** seldon (primary). squiddy is used through its CLI and never edited. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-036 ADDENDUM 12 (R21 the library arm searches a list, R22 the bridge); squiddy DN-056 R-246 (held bytes under the archive root); squiddy DN-049 R-212 (the inbox); squiddy DN-055 R-241 (robots.txt is read before a fetch); the operator's rules: a host that refuses is recorded with its posture and marked manual, nothing is declined before every route is tried, no step is handed to the operator.
**Model:** primary
**Spend:** est. 0.7M tokens. Basis: SEL-036 used 0.52M for the whole build; this is one restore, about 31 fetches with their stubs, one rebuild (87 min of parse last time, mostly two OMG PDFs already parsed and staged), three short errata.
**Network:** allowlist: api.openalex.org, api.crossref.org, api.datacite.org, api.github.com, doi.org, arxiv.org, github.com, raw.githubusercontent.com, discovery.ucl.ac.uk, content.scirp.org, www.jstage.jst.go.jp, content.iospress.com, jbiomedsem.biomedcentral.com, systematicreviewsjournal.biomedcentral.com, publikationen.bibliothek.kit.edu, journals.plos.org, ojs.aaai.org, www.ncbi.nlm.nih.gov, pmc.ncbi.nlm.nih.gov, www.ibm.com, deepmind.google, nvlpubs.nist.gov, www.ecfr.gov, www.w3.org, slsa.dev, www.rfc-editor.org, www.loc.gov, public.ccsds.org, www.gao.gov, oig.nasa.gov, cognitect.com, www.cdc.gov, randomlabs.ai, www.who.int, iris.who.int, ndsa.org, osf.io, nodis3.gsfc.nasa.gov, www.anthropic.com, pqdtopen.proquest.com
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon.yaml's `dispatch` block and `graphs/seldon-biblio`)
**Parts:** A 0.20, B 0.35, C 0.25, D 0.20.
**Premises:**
- premise: the graph's record is on main | check: test -f graphs/seldon-biblio/graph.yaml
- premise: the inbox exists and is empty | check: test -f graphs/seldon-biblio/intake/inbox/.gitkeep
- premise: the primary holds no served release | check: sh -c "! test -f graphs/seldon-biblio/exports/seldon_biblio_graph.json"

Read the SEL-036 RESULT first; its last three sections are this task's inputs.

## The condition (measured 2026-11-11 21:30 EST, primary checkout)

1. `seldon prior-art search "suspect link" --arm library` answers `graph seldon-biblio: unavailable: release_unavailable ... no served export at graphs/seldon-biblio/exports/seldon_biblio_graph.json`. SEL-036 built and released the graph in a worktree; the export, the index and the parse intermediates are gitignored, so the merge brought the record and not the release. Its RESULT left three shell steps for "operator or Desktop". Two days later nobody had run them, and SEL-035 wrote its design note with no seldon-biblio receipt for that reason. A release that exists only if a person runs a copy is not built.
2. 35 entries are marked for manual acquisition. 27 of them were never refused by anyone: their hosts were simply not on SEL-036's Network line. 4 have no URL in the note. Only 4 (dl.acm.org) drew a real HTTP 403.
3. SEL-036's resolution found citations in two governed notes that are wrong: `seldon_architectural_decisions.md` gives Saga the DOI `10.1145/3514221.3526052` (the work is `...3526049`); `cc5_sleep_function_architecture.md` attributes four works to the wrong authors ("Adler et al. 2021" is Saeedi, Peukert and Rahm, ESWC 2020; "Xiang et al. 2025" SplitE is Wang et al.; "Li et al. 2024" KG-LLM is Shu et al.; "Ebraheem et al." for arXiv:2104.03986 is Jain, Sarawagi and Sen, PVLDB 2021).

## What to build

**A. The release lives where the gate reads it, without a person.** Install release `20261109_sel036b` into the primary checkout from `~/kg-archive/seldon-biblio/build_outputs/20261109_sel036b/` (SEL-036's staged outputs; `$SELDON_PRIMARY_CHECKOUT` names the primary), `squiddy init graphs/seldon-biblio --check` clean, `git status --short graphs/` empty. Then declare `graphs/seldon-biblio/work`, `graphs/seldon-biblio/exports` and `graphs/seldon-biblio/corpus/parsed` in `dispatch.worktree_links` so a build in any later worktree writes the primary's directories. Test: a worktree build's served export is the primary's file. If `worktree_links` cannot carry this (say why), stop the Part and report; do not invent a second mechanism.

**B. Fetch.** For the 27 off-allowlist entries and the 4 without a URL (find the canonical free copy first: WHO TRS 1033 Annex 4; NDSA Levels of Digital Preservation v2.0; NASA NPR 7150.2 for SWE-072; Anthropic, "Lessons from Building Claude Code: Seeing Like an Agent"): read robots.txt (the step SEL-036's fetcher skipped), fetch through the graph's acquisition path into the archive root, write the form-feed `.txt` derivative, fill each stub (`inbox_source_url`, `inbox_obtained_from`, `inbox_licence`, `inbox_stated_by`). Also fetch OpenFastTrace's user-guide child pages (SEL-036 held only the index). Check two entries before keeping them: `mayer2009multimedia` (OpenAlex's OA location may not be the book) and `clelandhuang2012traceability` (the URL is a table of contents; keep it as that, labelled). A host that refuses is recorded with status, first bytes and time, and stays `acquisition: manual`. Do not retry dl.acm.org.

**C. Rebuild and prove.** `squiddy build` with extraction closed, as SEL-036 ran it; every release gate passing; the new release served in the primary. Then, from the primary, the five queries of SEL-036 Part F through `seldon prior-art search --arm library`: each must return `graph seldon-biblio` rows. Record the counts table again (cataloged, acquired with text, metadata-only, manual, declined) and the exact list still manual, with URL and posture, for the Desktop thread's one browser pass.

**D. Errata.** One erratum file per note in condition 3, in the form `docs/design` errata already take (`*_erratum_*.md`, verified with the note), each line giving the cited string, the work it is, its identifier and the seldon-biblio entry id. Where a note cites a preprint whose published version is now the record, name both. The notes themselves are not rewritten.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.85M.

## Deliverables

A to D with the worktree-link test; the release served in the primary; the manual list; `cc_tasks/2026-11-11_SEL-037_seldon_biblio_is_served_in_the_primary_its_open_texts_are_fetched_and_the_notes_it_proved_wrong_get_errata_RESULT.md`.
