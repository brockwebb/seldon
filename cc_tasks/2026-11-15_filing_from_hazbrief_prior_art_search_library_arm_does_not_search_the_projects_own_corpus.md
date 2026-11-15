# Filing from hazbrief-mcp: `seldon prior-art search --arm library`, run for hazbrief, searches the operator's general library and seldon's bibliography and not hazbrief's own corpus; and its query-log lines stay uncommitted when the lease is held

**Kind:** filing
**Filed by:** hazbrief-mcp
**Author:** Desktop session hz-17, 2026-11-15 09:50 EST, at the operator's direction of 09:42 EST: "I don't know why the prior art searches those knowledge bases. It should point to the knowledge base of the project that it is. That could be an error with either Seldon or Squiddy."

## What hazbrief experienced

1. On 2026-11-15, three calls of `seldon_prior_art_search` with `arm = library` and `project_dir = /Users/brock/GitHub/hazbrief-mcp`, code `81552bc`:
   - "dense gas shallow layer time dependent": 41 rows from `graph library`, 51 from `graph seldon-biblio`
   - "SCIPUFF vertical resolution puff split dense": 43 and 50
   - "Jack Rabbit chlorine model comparison": 41 and 57
   Every row was from the operator's general library (arXiv papers on language models, quantum circuits, chemistry agents) or seldon's bibliography (OMG, RFC, W3C and software documents). No row was a dispersion source. The receipts name the releases `library_graph_20261110_sq133r_b.r1_2026-11-13.json` and `seldon_biblio_graph_20261111_sel037_2026-11-11.json`.
2. hazbrief holds its own corpus (`graphs/hazbrief-corpus`), which carries the SCICHEM technical documentation, the Hanna, Strimaitis and Chang evaluation report and the other dispersion sources its tasks cite. None of it was searched.
3. The consequence in hazbrief: the prior-art receipts under AD-036 for a hazbrief design note on dispersion come from graphs that hold nothing on the subject. A note passes or fails the gate without the project's own literature being consulted. The operator found on 2026-11-15 that no literature review had been made of a problem hazbrief had spent three days on; the gate did not catch it.
4. The first of the three calls reported "prior-art lines in /Users/brock/GitHub/hazbrief-mcp not committed: lease_held"; the next two reported "not committed: dirty_before_this_run". hazbrief's dispatcher held the lease for HB-186 at the time. `seldon_commit_governed` refuses `state/prior_art_queries.jsonl` (`outside_roots`). So a Desktop session that searches while a task runs leaves a tracked file modified that it has no tool to commit. hazbrief does not know whether the dispatcher's next pass commits it or refuses on it.

## What hazbrief does not know

Whether the graphs searched are set by hazbrief's own `seldon.yaml`, by seldon, or by the squiddy library release. hazbrief has not looked and proposes nothing.
