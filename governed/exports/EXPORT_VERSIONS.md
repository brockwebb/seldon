# Export versions

One row per versioned export, derived by `squiddy.registers` from the release diff and the
artifact. A version missing from this table does not exist as far as the graph is concerned.

| Version | File | Date | sha256 (first 16) | Nodes / edges | Contents |
|---|---|---|---|---|---|
| **20261002_sweep** | `governed_graph_20261002_sweep_2026-10-02.json` | 2026-10-02 | `22075f31de6b8962` | 2,102 / 2,194 | sweep 20261002_sweep: 111 admissions, 111 layer runs. Section 0 -> 1,495 (+1,495); Passage 0 -> 415 (+415); Document 0 -> 111 (+111); Citation 0 -> 48 (+48); Ruling 0 -> 33 (+33); Contains 0 -> 1,943 (+1,943); Mentions 0 -> 178 (+178); Cites 0 -> 48 (+48); DependsOn 0 -> 13 (+13); Extends 0 -> 12 (+12). Round-trip verified; 5,771,730 bytes. |
| **20261004_sel002_export_repair** | `governed_graph_20261004_sel002_export_repair_2026-10-04.json` | 2026-10-04 | `4dca25038e271853` | 2,129 / 2,224 | SEL-002 step 0: re-cut the export over the ledger SQ-008 left ahead of it (AD-032 admitted, export stale) no label moved. Round-trip verified; 5,904,030 bytes. |
