# CC Task: allow DesignNote as the source of a `cites` edge

**Date:** 2026-09-28
**Project:** seldon (`/Users/brock/GitHub/seldon`)
**Filed from:** regs-comment-pipeline, task e9f7e860 (`cc_tasks/2026-09-28_notebook_and_citations.md`), Issue opened there naming the blocked links.
**Governing doc:** `docs/design/AD-030_governed_documents_as_graph_content.md`, ruling AD-030-R7 (a citation edge carries a CiTO intent).
**Spend:** est. 200k tokens.
**Network:** none beyond git push.
**Model:** primary
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 1.0.
**Part map:** A is steps 1 to 4.
**Registration (2026-10-14, seldon DISP-c7, task defca7cc; AD-036-R12):** the eight header lines above and the
`check:`/`judgment:` marks on the success criteria were added so the filing could be registered (`criterion_unmarked`,
AD-037-R1; `parts_undeclared`, AD-037-R6). The estimate is the registering session's, for a one-line schema change and
its tests. Nothing else in this file was changed.

## Goal

A registered `DesignNote` can `cites` a `Citation` (and a `Result` or `Passage`), with the same edge properties (`cito_type`, `reason`, `raw_reference`) every other citing type gets.

## Motivating case

regs-comment-pipeline DesignNote `f7c57569` (`docs/research/2026-09-28_classification_design_notebook.md`) is a lab notebook whose section 5 lists 15 references, each tied to a decision with a stated CiTO intent (`uses_method_in`, `cites_for_information`, `disagrees_with`). The 15 are registered as `Citation` artifacts, 14 verified. Every `seldon link create <note> cites <citation>` is refused:

```
Error: 'DesignNote' cannot originate a 'cites' relationship. Valid from_types: ['PaperSection', 'Figure', 'Document', 'Section', 'Ruling']
```

A design note is where a project records why it adopted or departed from prior art (Standards Sections 7 and 7.5, operator doctrine section 1: "decision docs and specs name the prior art they implement or deliberately depart from"). Without this edge that grounding lives only in prose, and a stale or refuted citation cannot propagate to the decisions resting on it.

## Steps

1. Write the failing test first (Standards Section 5): in `tests/test_relationship_types.py`, a case asserting `validate_relationship(domain, "cites", "DesignNote", "Citation")` passes, and one creating the edge with `cito_type="uses_method_in"` through `create_link` and reading the property back.
2. `seldon/domain/research.yaml`, `relationship_types.cites.from_types`: add `DesignNote`. One-line change; add a comment naming this task and AD-030-R7.
3. Full suite green: `python -m dotenv -f .env run -- python -m pytest tests/ -v`.
4. Commit `feat: DesignNote may originate cites edges (AD-030-R7)`; push.

## Success criteria

- check: python -m dotenv -f .env run -- python -m pytest tests/ -q
  The new tests pass; nothing else in the suite changes.
- judgment: it runs in another repository against its own graph, with a citation id chosen there.
  From regs-comment-pipeline, `seldon link create --actor cc --from-name classification_design_notebook_2026_09_28 --rel cites --to-id <citation>` succeeds.

## Observed alongside (not in scope here; file separately if wanted)

- `seldon link create` has no option for edge properties, so the CiTO `cito_type` and `reason` this edge exists to carry can only be written through `seldon.core.artifacts.create_link(..., rel_properties=...)` from Python. The intended regs-comment-pipeline edges will be created that way unless a `-p KEY=VALUE` option lands first.
- There is no CLI or MCP command for a generic artifact state transition (DesignNote proposed -> active, Citation proposed -> verified per AD-030-R6). regs-comment-pipeline used `seldon.core.artifacts.transition_state` directly.

## What NOT to do

- Do not widen `to_types` or add new CiTO values.
- Do not touch any other relationship type.

## Addendum, 2026-09-28 (afternoon): ArchitecturalDecision as a `cites` source too

Filed from regs-comment-pipeline task c1ca8174 (`cc_tasks/2026-09-28_register_ad003_ad004_srs.md`). The same refusal hits
ArchitecturalDecision:

```
Error: 'ArchitecturalDecision' cannot originate a 'cites' relationship. Valid from_types: ['PaperSection', 'Figure', 'Document', 'Section', 'Ruling']
```

An AD is where a project names the prior art it adopts or departs from (the operator's doctrine section 1), so it is the
primary citing type, not an edge case. Extend step 2 to add **both** `DesignNote` and `ArchitecturalDecision` to
`relationship_types.cites.from_types`, and step 1's tests to cover both. Scope is otherwise unchanged: `from_types`
only; no change to `to_types` or the CiTO values.

Intended edges from regs-comment-pipeline, all `-[cites]-> Citation` with `raw_reference` = the reference line as the AD
writes it (in the AD's References section). Create them once the schema allows it:

| from | citation | cito_type |
|---|---|---|
| AD-003 0c11ee63 | broder1997resemblance a0778bea | uses_method_in |
| AD-003 0c11ee63 | leskovec2020mmds 68d01627 | uses_method_in |
| AD-003 0c11ee63 | reimers2019sentencebert 3866ec07 | uses_method_in |
| AD-003 0c11ee63 | grootendorst2022bertopic ac0c8ae8 | cites_for_information |
| AD-003 0c11ee63 | balla2021mass 2f60b455 | cites_for_information |
| AD-003 0c11ee63 | acus2021rec20211 de596ca9 | cites_for_information |
| AD-004 b9fd3e0e | usc44_3506 477dd28c | cites_for_information |
| AD-004 b9fd3e0e | census2018prafr dd08f30d | cites_for_information |
| AD-004 b9fd3e0e | acus2021rec20211 de596ca9 | cites_for_information |
| AD-004 b9fd3e0e | balla2021mass 2f60b455 | cites_for_information |
| AD-004 b9fd3e0e | statefarm1983 f6de0488 | cites_for_information |
| AD-004 b9fd3e0e | macqueen1998codebook 522c069c | uses_method_in |
| AD-004 b9fd3e0e | fereday2006rigor 225f437e | uses_method_in |
| AD-004 b9fd3e0e | krippendorff2018content 55e32cee | uses_method_in |
| AD-004 b9fd3e0e | cohen1960coefficient 645ae24d | uses_method_in |
| AD-004 b9fd3e0e | ranganathan1933colon ca29db82 | uses_method_in |
| AD-004 b9fd3e0e | broughton2006faceted 0a6559a7 | uses_method_in |
| AD-004 b9fd3e0e | dai2023llminloop 0eaa4a62 | uses_method_in |
| AD-004 b9fd3e0e | xiao2023codebook 48fa2d3c | uses_method_in |

Also observed, not in scope: `SRS_Requirement` has no path property and no edge to the AD or source it cites, so a
requirement's "(AD-003; Broder 1997)" provenance lives only in a text property. regs-comment-pipeline anchors its SRS file
with a DesignNote (note_type requirements) for the content hash; a requirements-document type, or `derives_from`
SRS_Requirement -> ArchitecturalDecision/Citation, would remove that workaround.

### Further intended edges, AD-004 revision R1 (regs-comment-pipeline task a637c17b, 2026-09-28)

| from | citation | cito_type |
|---|---|---|
| AD-004 b9fd3e0e | silla2011hierarchical 15bc5f34 | uses_method_in |
| AD-004 b9fd3e0e | kostoff1997tomography 25409952 | cites_for_information |
| AD-004 b9fd3e0e | blei2003lda 97d62dbd | cites_for_information |
| AD-004 b9fd3e0e | grootendorst2022bertopic ac0c8ae8 | cites_for_information |
| AD-004 b9fd3e0e | jigsaw2018toxic 3600a88d | cites_for_information |
| AD-004 b9fd3e0e | perspective_attributes d90f3fcf | cites_for_information |
| AD-004 b9fd3e0e | cochran1977sampling 27eb2675 | cites_for_information |

AD-004 R1 also cites Krippendorff 2018 again; that edge is already in the table above.
