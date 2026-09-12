# Export versions

One row per versioned export, derived by `squiddy.registers` from the release diff and the
artifact. A version missing from this table does not exist as far as the graph is concerned.

| Version | File | Date | sha256 (first 16) | Nodes / edges | Contents |
|---|---|---|---|---|---|
| **backfill_20260912** | `governed_graph_backfill_20260912_2026-09-12.json` | 2026-09-12 | `645d255edc929d6f` | 2,082 / 2,156 | sweep backfill_20260912: 97 admissions, 97 layer runs. Section 0 -> 1,391 (+1,391); Passage 0 -> 389 (+389); Ruling 0 -> 168 (+168); Document 0 -> 97 (+97); Citation 0 -> 37 (+37); Contains 0 -> 1,948 (+1,948); Mentions 0 -> 155 (+155); Cites 0 -> 37 (+37); DependsOn 0 -> 9 (+9); Extends 0 -> 7 (+7). Round-trip verified; 5,516,859 bytes. |
| **topup_20260912** | `governed_graph_topup_20260912_2026-09-12.json` | 2026-09-12 | `7a3306c6cc6e0c59` | 2,097 / 2,172 | sweep topup_20260912: 1 admissions, 98 layer runs. Section 1,391 -> 1,398 (+7); Passage 389 -> 393 (+4); Ruling 168 -> 171 (+3); Document 97 -> 98 (+1); Contains 1,948 -> 1,962 (+14); Mentions 155 -> 157 (+2). Round-trip verified; 5,563,027 bytes. |
