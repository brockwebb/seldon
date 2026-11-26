# Filing from factory: the prior-art search does not read four registered repositories, and a need stated in a thread cannot enter the graph in that turn

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-26
**Reporter:** factory FAC-17 (`cc_tasks/2026-11-26_FAC-17_what_the_operator_says_becomes_a_need_in_the_graph_with_a_disposition_and_a_check_fails_when_one_is_left_in_a_file.md`; factory F-034, design note `docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md`)

## Why this is filed

The operator, 2026-11-26 08:54 EST: "we discuss things and then later on I find that they were never implemented ...
or we never had reasons why we didn't do something, or we go back and rediscover something." Factory now records each
thing he states as a stakeholder need with a disposition (F-034). Two gaps in seldon keep that from closing the loop,
and two more were met while doing it.

## 1. The internal arm of the prior-art search reads six of the ten registered repositories

`prior_art.internal_roots` in seldon's `seldon.yaml` lists seldon, squiddy, ai-readiness-kg, arnold, icsp_notebook,
Wintermute and the workbench audit. It does not list factory, hazbrief-mcp, aacps-ai-policy or critical-thinking-ai,
all registered in factory's `registry.md` and `seldon.yaml` `portfolio.repositories`. So a design note or a decision
written in any of those four is never found by the search that exists to stop rediscovery.

Evidence, a search run from factory at 2026-11-26 ~14:50Z (receipts as printed):

- internal receipt: query "requirements elicitation" | repo seldon@61e01e87739595ad636125bab1a053c34b9ca3db | hits none
- internal receipt: query "requirements elicitation" | repo squiddy@057e13a3e6e6cbd9ecf5d4398b5aeea0db268c50 | hits docs/design/2026-09-30_scope_not_questions_at_the_input_wall.md:25, docs/DECISIONS_INHERITED.md:489
- internal receipt: query "requirements elicitation" | repo ai-readiness-kg@951a1e5d3880e0b46195a8d9ce83f819a2b5ad9c | hits none
- internal receipt: query "requirements elicitation" | repo arnold@8a0c94bc4f09d2420d8c4a9bed1e6b169251ea5d | hits none
- internal receipt: query "requirements elicitation" | repo icsp_notebook@990785776b53b0c9dda4d6e47aad7d02e04f86a5 | hits none
- internal receipt: query "requirements elicitation" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "requirements elicitation" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

No receipt names factory, although factory's `docs/se/strs.md` and its 56 stakeholder needs are exactly what this query
should find. The FCT-6 coordinator saw the same set at 08:58 EST.

What is needed: every registered repository's notes, and its requirement nodes (the `SRS_Requirement` artifacts in
its event store, which are the requirements; the `docs/se/*.md` tables are only their projections), in the internal
arm. One source of the list, not a second hand-kept copy: factory's `portfolio.repositories` already names them.

## 2. The Desktop session has no MCP verb for `seldon req add`

The coordinator works in a Desktop thread through seldon-mcp. It can write a decision and a task, but not a
requirement: `seldon req add` and `seldon req update` are CLI-only. So a need the operator states in a thread cannot
enter the graph in the turn it is said (factory F-020's rule); it waits for a dispatched session, and until then it
lives in a file, which is the failure F-034 exists to remove.

What is needed: `seldon_req_add` and `seldon_req_update` on seldon-mcp, with the same fields and refusals as the CLI.

## 3. A requirement has no disposition property

F-034 needs every stakeholder need to carry a disposition (built, planned with a task, deferred with a reason and an
ending condition, declined with a reason, undecided). `SRS_Requirement` in `seldon/domain/research.yaml` has no such
property, so factory writes it as the first clause of `note`, in a form its check parses
(`disposition: deferred; reason: ...; ends when: ...`). The Issue type already has `disposition` and
`disposition_evidence` (SEL-021). A first-class property, shown in the projection's Status cell and checked by
`seldon docs check`, would let every project do this without a parser of its own.

## 4. `seldon decision accept --from` without `source:` writes a record that breaks the register

In factory's FAC-17 worktree, `seldon decision accept --from f034.yaml --decided-by desktop` with a YAML holding
`id`, `kind`, `statement`, `scope`, `rationale` and `review_only` but no `source` wrote
`docs/decisions/register/pending/00001_..._factory-f-034_accept.yaml` and then printed
`FATAL: event None (accept) names factory:F-034, which no earlier file created`. Every later `seldon decision check`
and `seldon decision show` failed the same way until the file was deleted by hand. `event_form` reads an accept
with no `source` as a transition of an existing record, but the write was not refused first. With `source.path` and
`source.lines` the record was written and the register was clean.

What is needed: a new-record accept with no `source` is refused before any file is written (as a wrong `source.text`
or `source.sha256` already is), with the message naming the missing key.
