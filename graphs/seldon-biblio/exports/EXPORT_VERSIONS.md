# Export versions

One row per versioned export, derived by `squiddy.registers` from the release diff and the
artifact. A version missing from this table does not exist as far as the graph is concerned.

| Version | File | Date | sha256 (first 16) | Nodes / edges | Contents |
|---|---|---|---|---|---|
| **20261109_sel036** | `seldon_biblio_graph_20261109_sel036_2026-11-09.json` | 2026-11-09 | `6a92c10d25362669` | 427 / 433 | SEL-036 Parts C and D: the first build of seldon-biblio Person 0 -> 320 (+320); Work 0 -> 63 (+63); Standard 0 -> 19 (+19); Decision 0 -> 15 (+15); Software 0 -> 10 (+10); AuthoredBy 0 -> 326 (+326); SupportsDecision 0 -> 107 (+107). Round-trip verified; 346,671 bytes. |
| **20261109_sel036b** | `seldon_biblio_graph_20261109_sel036b_2026-11-09.json` | 2026-11-09 | `76f754f493f86618` | 448 / 456 | SEL-036 Parts C and D: the second build, the documentation snapshots as .txt and li2024kgllm from arXiv Person 320 -> 327 (+7); Work 63 -> 77 (+14); AuthoredBy 326 -> 333 (+7); SupportsDecision 107 -> 123 (+16). Round-trip verified; 364,324 bytes. |
| **20261111_sel037** | `seldon_biblio_graph_20261111_sel037_2026-11-11.json` | 2026-11-11 | `076422bb8382009f` | 490 / 498 | SEL-037 Part C: SEL-036's release plus the open texts Part B fetched (robots.txt read first) Person 320 -> 327 (+7); Work 63 -> 119 (+56); AuthoredBy 326 -> 333 (+7); SupportsDecision 107 -> 165 (+58). Round-trip verified; 410,642 bytes. |
