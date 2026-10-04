# SEL-002 ADDENDUM 01: AD-033-R10 in Part A

Written before SEL-002 was dispatched; read with it.

Registering SEL-002 bound AD-030-R14 ("the Document node plus its Ruling nodes is the decision record") and AD-029
Addendum 029-A (label binding). AD-033-R10 supersedes R14 and keeps 029-A. In Part A, add:

1. The `Decision` label joins Addendum 029-A's label set, and the lint test that asserts the set covers every label a
   Cypher write in `seldon/core/` or `seldon/commands/` creates passes with it. Every read that traverses a
   relationship from a `Decision` node binds `:Artifact`.
2. Legacy `ArchitecturalDecision` and `DesignNote` nodes are not mutated. A planted test asserts the count of each is
   unchanged after the DB-1 seed.
3. The seed writes the superseding record `seldon:AD-033-R10` superseding `seldon:AD-030-R14` through the command,
   as every other baseline transition.
