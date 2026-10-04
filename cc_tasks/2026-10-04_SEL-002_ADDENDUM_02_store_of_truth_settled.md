# SEL-002 ADDENDUM 02: AD-033-R11, the store-of-truth question closed

Written before SEL-002 was dispatched; read with it.

The operator decided on 2026-10-04: the append-only, hash-chained event ledger is the record of truth for every
graph, every Seldon project and the register; Neo4j is the live working store, written only by ledger replay and
proven by the parity gate; the manifest is events in that ledger; YAML and REGISTER.md are rendered. AD-033-R11
carries the decision and its grounding.

1. Seed `seldon:AD-033-R11` as accepted, `decided_by: operator`, `operator_stated: true`, receipt this addendum and
   AD-033-R11, superseding `squiddy:R-04`. It amends `squiddy:R-08`, `squiddy:DI-070`, `squiddy:DI-163`,
   `squiddy:DI-242` (direction) and `seldon:AD-030-R5` (reading: "the graph" is the graph's ledger).
2. F04 and F06 are resolved by R11 (AD-033 section 5). Neither goes on the override list.
3. Correct the prose agents read first, so the question stops reopening. These are not dispatched records, so they
   are edited, each in its own commit naming AD-033-R11:
   - `squiddy/CLAUDE.md`, "The one invariant": replace the sentences saying Squiddy does not mandate which store is
     truth, and that an Arnold graph may run graph-as-truth, with R11's first two sentences.
   - Any `CLAUDE.md`, README or conventions file in squiddy, seldon or arnold that names Neo4j, the YAML manifest or
     `manifest.yaml` as authoritative or as the record (search for "authoritative", "source of truth",
     "graph-as-truth", "store of truth"). List every hit and the change in the delivery report.
4. Exit check added: a search of the three repositories' agent-read files (`CLAUDE.md`, `docs/conventions/`,
   READMEs) finds no sentence naming a store other than the ledger as the record of truth.
