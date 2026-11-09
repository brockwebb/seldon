# SEL-036: Seldon gets a bibliographic graph: every source its design notes cite is a resolved work with citation metadata, its text where the licence allows, and a manifest entry with its access posture

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-09, on the operator's order: "All those sources that we are quoting must have a citation and added to the Seldon knowledge graph ... at least we can create the corpus inbox and download those ... we need all citation and metadata for the manifest."
**Repo:** seldon (primary; the new graph lives in it). squiddy is used through its CLI and never edited. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-030 (governed documents as graph content; its `Citation` artifacts are this task's harvest); AD-036 (prior art; its `library` arm); AD-013 ADDENDUM 01 section 2 (seven external sources "cited by their published names and were not fetched"); squiddy DN-049 R-212 (every graph has `intake/inbox/`); squiddy DN-034 (one `visibility` key); squiddy DN-037 (acquisition before ingest); the operator's standing rules: the manifest records every document considered including declines with reasons; a host that blocks machine pulls is recorded with its access posture and marked for manual acquisition; git is not a file archive. Number new rulings under AD-036.
**Model:** primary
**Spend:** est. 1.3M tokens (session). Basis: one graph init from a spec modelled on squiddy's `graphs/biblio`, a harvest of 72 governed citations plus about 25 named below, identifier resolution by HTTP, acquisition of open texts, squiddy's normal admit, one bridge, one config change. Model calls for extraction run on squiddy's configured extraction instrument and its own spend band, not this session's.
**Network:** allowlist: api.openalex.org, api.crossref.org, doi.org, export.arxiv.org, arxiv.org, api.semanticscholar.org, github.com, raw.githubusercontent.com, pypi.org, doorstop-dev.github.io, strictdoc.readthedocs.io, sphinx-needs.readthedocs.io, cog.readthedocs.io, nedbatchelder.com, www.incose.org, www.omg.org, www.iso.org, standards.ieee.org, ieeexplore.ieee.org, dl.acm.org, link.springer.com, danieleades.github.io, argondigital.com
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (adds `graphs/`, edits seldon.yaml's `prior_art` block and `seldon/core/prior_art.py`)
**Parts:** A 0.15, B 0.25, C 0.20, D 0.15, E 0.15, F 0.10.
**Premises:**
- premise: Seldon's governed graph holds the citation strings its notes carry | check: test -d governed
- premise: squiddy's bibliographic graph spec is the model | check: test -f ../squiddy/graphs/biblio/graph.yaml
- premise: squiddy init scaffolds an inbox | check: test -f ../squiddy/tests/test_sq019_init_inbox.py
- premise: a working consumer graph with an inbox exists to copy from | check: test -d ../hazbrief-mcp/graphs/hazbrief-corpus/intake/inbox
- premise: the prior-art library arm names one graph today | check: grep -q "graph: ../squiddy/graphs/library" seldon.yaml

## The condition

Seldon's governed graph parses its own design notes, task files and handoffs into Document, Section, Ruling, Passage and `Citation` artifacts (AD-030): 72 `Citation` nodes on 2026-11-09, each a string cut from a note (`docs_design_ad_029_task_precedence@kelley_walker_1959`). None is resolved to a work, an identifier, a licence or a text. The prior-art gate's library arm reads squiddy's `library` graph, the works cited in the Claude conversation export, which holds almost nothing on requirements engineering: SEL-033's two library receipts returned model-training rows, so AD-013 ADDENDUM 01 cited 29148, ReqIF, SysML v2, DOORS, Gotel and Finkelstein, Cleland-Huang and Cog by name only. SEL-035 (086d89ff) cites seven more, fetched by the Desktop thread but held nowhere. Seldon has a graph of what it says and no graph of what it rests on.

## The seed set

1. **The 72 governed `Citation` artifacts**, read from `seldon-seldon-self` (`MATCH (c:Citation) RETURN c`), deduplicated to works (one work cited by several notes is one entry with several `cited_in`).
2. **AD-013 ADDENDUM 01 section 2:** ISO/IEC/IEEE 29148:2018; OMG ReqIF 1.2; OMG SysML v2 (requirement, satisfy, verify, derive); IBM DOORS (formal module documentation); Gotel and Finkelstein 1994, "An analysis of the requirements traceability problem" (ICRE); Cleland-Huang, Gotel, Zisman (eds.) 2012, *Software and Systems Traceability* (Springer), and Cleland-Huang et al. 2014, "Software traceability: trends and future directions" (FOSE); Cog (Ned Batchelder).
3. **SEL-035's list, fetched 2026-11-09:** Doorstop (https://doorstop-dev.github.io/doorstop/, and Browning and Adams, "Doorstop: Text-Based Requirements Management Using Version Control", 2014); OpenFastTrace (https://github.com/itsallcode/openfasttrace, `doc/user_guide.md`); StrictDoc (https://strictdoc.readthedocs.io/en/stable/); sphinx-needs (needtable and dynamic functions pages); Cog `running.html`; ISO/IEC/IEEE 15288:2023 (verification methods); Scukanec and van Gaasbeek, "A Day in the Life of a Verification Requirement", INCOSE IS 2010; ArgonDigital, "Use of multiple verification methods" (grey literature, recorded as such); Requiem (https://danieleades.github.io/requiem/, suspect-link fingerprints).

Software and standards are entries too (biblio's Standard and Software classes): a tool is cited by its repository, release and documentation URL.

## What to build

**A. The graph.** `seldon/graphs/seldon-biblio/graph.yaml`, modelled on `../squiddy/graphs/biblio/graph.yaml` (classes Work, Standard, Software, Person, Organization, Decision, ExternalReference and their edges; `policy: own_record_or_public`; `visibility: public`), with a scope in the operator's terms: "the works, standards and software Seldon's design notes and tasks rest on, each resolved to its identifier, so a ruling's prior art is a link and not a name". Then `squiddy init` through squiddy's own console script (seldon.yaml `project_new.squiddy_command`), and `squiddy init --check` clean. The inbox is `intake/inbox/`. Source files are stored where `hazbrief-corpus` stores them per squiddy's config; no PDF or HTML capture is committed to git (gitignore what the layout leaves in the tree), and the manifest carries each file's sha256, URL and retrieval time.

**B. Catalog: citation and metadata for every entry, zero model calls.** For each seed: resolve through OpenAlex, then Crossref, then doi.org, then Semantic Scholar, then the publisher or project page, in that order, recording which authority answered. Each manifest entry carries kind (work, standard, software, grey), title, authors or body, year, venue or publisher, edition or release, DOI or OpenAlex id or ISBN or standard number or repository and version, canonical URL, licence and its URL, and `cited_in` (every governed note and task that cites it). An entry no authority confirms is declined only after every authority above was tried, with each attempt and its answer kept (the operator's rule of 2026-09-15). A standard behind a paywall (ISO, IEEE) is a metadata-only entry with `access: purchase`, never declined.

**C. Acquire.** Download every open text (open-access PDF, arXiv, project documentation pages as HTML snapshots, the README and docs of each tool at the release cited) into the store, through the graph's acquisition path so each file gets its stub. A host that refuses the pull (403, bot wall, JavaScript-only) is recorded with its access posture and evidence (status code, the response's first bytes, the time) and marked `acquisition: manual`. If this session has a browser tool, use it for those before marking them; if it does not, mark them and list them in the RESULT: the Desktop thread fetches them with the operator's browser into `intake/inbox/` (the route validated 2026-10-23) and fills the stubs.

**D. Admit.** Run squiddy's normal admit over every acquired entry, as the graph's config declares it (extraction instrument and spend band are squiddy's, not this task's). Metadata-only entries are admitted as records. Report counts: cataloged, resolved, acquired, manual, metadata-only, declined, admitted.

**E. Bridges.** (1) Each governed `Citation` artifact gets a `resolves_to` link to its entry's identifier in seldon-biblio (an `ExternalReference` with the graph and the id; a pointer, never a copy), so the governed graph answers which works a ruling rests on. Domain-config edge added only if none fits; say which. (2) `prior_art.library` accepts a list of graphs, searched together, and seldon.yaml names both `../squiddy/graphs/library` and `graphs/seldon-biblio`; a receipt names the graph its rows came from; existing receipts keep verifying (they name the squiddy library release). Ruling under AD-036, in an addendum with its prior-art receipts, `prior-art verify` passing before the code.

**F. Proof.** Re-run the library searches AD-013 ADDENDUM 01 ran ("requirements traceability matrix", "trace link maintenance") and three more ("suspect link", "generated region markers", "verification method inspection analysis demonstration test"); record in the RESULT whether rows from seldon-biblio now answer them. List every `acquisition: manual` entry with its URL and posture, for the Desktop thread.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.6M.

## Deliverables

The graph, its manifest and inbox; the bridges; the AD-036 addendum and its ruling; tests for the multi-graph library arm and the bridge; `cc_tasks/2026-11-09_SEL-036_seldon_gets_a_bibliographic_graph_every_cited_source_is_a_resolved_work_with_its_metadata_and_text_RESULT.md` with the counts and the manual list.
