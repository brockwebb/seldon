# CC Task: Wintermute Sleep-Function Architecture Specification

**Date:** 2026-04-18
**Project:** Seldon (`/Users/brock/Documents/GitHub/seldon/`)
**Parent ResearchTask:** `38b0698b` (Evolution Burst 2026-04 Plan Anchor)
**Spec ResearchTask:** `de84cb6a`
**Scope:** Evolution burst 2026-04 — CC5 of 5

---

## Goal

Produce a complete architectural specification for Wintermute's three sleep functions: **collapse/dedup**, **disambiguate**, and **AI-proposed-edge-inference**. The spec is a design document, NOT implementation.

**Architectural center claim (candidate AD-023):** Wintermute's distinctive value is the sleep-function layer, not ingestion-plus-lookup. The graph is substrate. Sleep functions are product. Without them, Wintermute is strictly worse than claude-mem (which has commodity capture solved). With them, Wintermute is the only system in the ecosystem building offline graph cognition.

The deliverable feeds Phase C synthesis and, if the spec argues for a new AD, includes the AD-023 draft.

**Design only. No code. No Wintermute changes.**

---

## Prerequisites

1. CC1 is done or in progress — its Q4 (claude-mem adopt-vs-extract) output informs where sleep functions sit relative to commodity capture. If CC1 isn't done, proceed with Brock's stated position in the handoff: claude-mem could handle capture; Wintermute owns sleep functions above it.
2. Output directory: `/Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/` (exists from CC2).
3. **Wintermute is NOT currently a Seldon-managed project** (no `seldon.yaml` at `/Users/brock/Documents/GitHub/wintermute/` per CC2 findings). Therefore: deliverable lives in seldon's graph and filesystem. When Wintermute is initialized as Seldon-managed, the spec gets re-homed via ADR pointer. For now, reference it from the seldon graph with a note.

---

## Steps

### 1. Literature scan (brief — half an hour, max)

Do NOT reinvent. Search for prior art on:

- **Continuous entity resolution on knowledge graphs** — not batch dedup. What's been tried, what works, what fails.
- **Probabilistic / Bayesian edge inference on knowledge graphs** — belief propagation, Markov logic networks, embedding-based link prediction. Especially: why these often fail on sparse heterogeneous KGs.
- **Human-in-the-loop graph curation patterns** — arbitration queues, confidence thresholds, merge-proposal UIs.
- **Prior art Brock has in memory:** sift-kg (three-layer entity resolution — SemHash/Unicode deterministic pre-dedup at 0.95 threshold → LLM-proposed merges with confidence scores → human review via editable YAML). Cross-reference.

Record 5–8 references. For each: one-sentence summary, one-sentence "applicable here because" or "not applicable because."

Web search is fine. arXiv for recent work. Don't go down a rabbit hole — this is a literature pointer, not a literature review.

### 2. Define each sleep function

For EACH of the three, fill this spec template completely:

```
### Sleep Function N: <name>

**Purpose (one sentence):**

**Trigger / cadence:**
- Nightly? Weekly? On event? On manual invocation? Be specific.
- What triggers a run — graph delta threshold, time, explicit command?

**Input:**
- Exact graph state / subset / events required.
- Upstream dependencies: what must be fresh before this runs?

**Process:**
- Step-by-step. Not pseudocode, but unambiguous natural-language steps
  that a Claude Code session could turn into code.
- For steps that call LLMs: which model tier (local cheap triage vs API reasoning),
  approximate prompt shape, expected output format.
- For steps that emit proposals for human arbitration: what the arbitration
  queue looks like (file? graph state? CLI command?).

**Output:**
- Event log entries (schema).
- Graph mutations (always event-sourced — what event types).
- Notifications / arbitration queue additions.

**Compute budget:**
- LLM call count per cycle at three graph sizes: 1K nodes, 10K nodes, 100K nodes.
- Estimated cost in USD per cycle at current Gemini Flash pricing (~$0.075/M input, $0.30/M output).
- Pareto 4-64 principle applied: which 4% of the graph drives 64% of the work?

**Failure modes:**
- What can go wrong?
- Silent failures to watch for (wrong merges, missed splits, confabulated edges).
- Rollback strategy (event-sourced, so: which events to revert, how to audit).

**Measurement — how do we know this is producing useful signal vs noise:**
- Precision proxy: fraction of proposals human-approved vs human-rejected
- Recall proxy: ???  (be honest if there's no easy recall proxy)
- Outcome proxy: downstream effect on graph quality (cluster coherence,
  retrieval accuracy) — even if future work
- Specific metric names that CC4's dashboard should track (crossref to CC4)
```

#### Sleep Function A: Collapse / Dedup

Architectural constraint (per Brock memory, sift-kg pattern): **three-layer**.

1. Deterministic pre-dedup: SemHash, Unicode normalization, configurable similarity threshold (0.95 baseline).
2. LLM-proposed merges with calibrated confidence scores.
3. Human arbitration via editable YAML or CLI-reviewed queue.

Compute budget discipline: targeted to **recently-changed neighborhoods only**, not full-graph scans. Define "recently-changed" precisely (e.g., nodes touched in last 24h + 1-hop neighbors).

Address: what confidence threshold auto-accepts vs queues for human? Be specific. Don't hedge with "configurable" — give a starting value and say "tunable."

#### Sleep Function B: Disambiguate

The inverse of collapse. Detect entities that should be split.

Triggers that suggest a split-needed state:
- High intra-cluster variance (nodes merged into one entity have contradictory attribute values)
- Contradictory evidence (edges pointing to incompatible states)
- Embedding-space bimodality (entity's aggregated embedding is clearly two clusters)

Process: same arbitration pattern as collapse. LLM proposes split with rationale; human approves/rejects.

Failure mode unique to disambiguate: splitting an entity that was correctly merged. Rollback: event-sourced merge can be replayed.

#### Sleep Function C: AI-proposed-edge inference

**Naming discipline required.** The original spec said "Bayesian-edge inference." Interrogate this:

- If we mean belief propagation over a probabilistic graphical model, say so and justify the compute cost. Likely impractical on heterogeneous KGs.
- If we mean LLM-proposed edges with confidence scores and human arbitration (sift-kg middle path) — call it that. "AI-proposed-with-human-arbitration" is accurate. "Bayesian" is not.
- If we mean something in between (e.g., confidence from an ensemble of LLM proposals, treated as a posterior-like estimate) — describe precisely what and don't dress it in Bayesian language.

Pick the accurate name. The spec uses that name consistently.

Input: entity pairs that don't currently have edges but appear connected via (a) shared neighbors, (b) embedding similarity, (c) co-occurrence in source documents.

Process: candidate-pair generation → LLM proposes edge type + confidence → human arbitration for low-confidence, auto-accept for high-confidence (with specific threshold).

### 3. Cross-cutting concerns

A section covering:

**Ordering & interaction between sleep functions:**
- Does collapse run before disambiguate or after? Why?
- What happens if collapse merges two entities that disambiguate then wants to split?
- Edge inference must run AFTER collapse/disambiguate stabilize, or edges get proposed on about-to-be-invalid entities.

**Event sourcing discipline:**
- Every sleep-function mutation is an event in the Wintermute event log.
- Event types: `merge_proposed`, `merge_accepted`, `merge_rejected`, `split_proposed`, `split_accepted`, `split_rejected`, `edge_proposed`, `edge_accepted`, `edge_rejected`.
- Full replay must reconstruct graph state including the curation history.

**Human arbitration workflow:**
- Where does the arbitration queue live? Proposal: editable YAML files under `~/.wintermute/arbitration/` with `<date>_<type>.yaml` naming.
- How does the user review? CLI command (`wintermute arbitrate`) or passive file editing?
- What's the SLA assumption? Does the queue grow unbounded, or does the system pressure-relieve (auto-accept after N days? escalate high-confidence proposals?).

**Single-point-of-failure resistance (per handoff governing claim #2):**
- Sleep functions invoke LLMs. Single-model dependency on Gemini Flash creates a SPOF.
- Spec should name: where the architecture is single-model today, where it should be ensemble, what the cheapest path to ensemble looks like (LiteLLM multi-provider).
- Do NOT require ensemble in v1. Do name it as a v2 requirement.

### 4. Integration with CC4 observability dashboard

List the metrics CC4 should expose for sleep-function observability:

- `sleep.collapse.proposals.per_cycle` (count)
- `sleep.collapse.accepted.per_cycle` (count)
- `sleep.collapse.rejected.per_cycle` (count)
- `sleep.collapse.auto_accepted_rate` (fraction)
- Parallel metrics for split and edge.
- `sleep.arbitration_queue.size` (gauge)
- `sleep.arbitration_queue.oldest_pending_days` (gauge)
- `sleep.compute.llm_calls.per_cycle` (count)
- `sleep.compute.cost_usd.per_cycle` (gauge)

Format these as a table with columns: metric name | type | definition | threshold-for-attention.

The dashboard's Q-a curation-rate panel is currently a stub (per CC4 spec). This list unblocks it once sleep functions are implemented.

### 5. AD-023 draft

If the spec argues for a new AD (it does — that's the framing), include the draft at the end of the design doc. Format:

```markdown
## AD-023 Draft: Wintermute Sleep Functions as Architectural Center

**Status:** Proposed, 2026-04-18.

**Context:** <1 paragraph — why this AD is needed now>

**Decision:** <1-2 paragraphs — what is being committed>

**Consequences:**
- Positive: <bullets>
- Negative / cost: <bullets>
- Reversibility: <how hard to undo if wrong>

**Relation to prior ADs:**
- AD-001 (ANTS → Seldon): this extends the event-sourced pattern into Wintermute
- AD-017 (Central Ontology): sleep functions operate against ontology-aligned terms
- AD-019/020 (Audit pipeline): similar authority model — AI proposes, human arbitrates
- AD-022 (CLI-default, if drafted): arbitration may be CLI-driven
- AD-024 (Observability, if drafted): sleep functions are prime observability target

**Open questions deferred:**
- <list what the AD explicitly does not decide>
```

### 6. Write the deliverable

**Path:** `/Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md`

Structure:

```markdown
# CC5: Wintermute Sleep-Function Architecture — 2026-04-18

**Date:** 2026-04-18
**Status:** Design spec. Not yet implemented.
**Scope note:** Wintermute is not currently a Seldon-managed project.
  When it is initialized as Seldon-managed, this spec migrates there.
  For now it lives in seldon's docs/design/evolution_burst_2026-04/.

## Architectural claim

(The AD-023 thesis stated upfront, 2–3 paragraphs. Why sleep functions are
the distinctive value. Why without them Wintermute is redundant.)

## Literature scan

(5–8 references, with applicability notes)

## Sleep Function A: Collapse / Dedup

(full spec per Step 2 template)

## Sleep Function B: Disambiguate

(full spec)

## Sleep Function C: AI-proposed-edge inference

(full spec, with the naming discipline section prominent)

## Cross-cutting concerns

(ordering, event sourcing, arbitration workflow, SPOF resistance)

## Dashboard integration

(table of metrics per Step 4)

## AD-023 Draft

(per Step 5)

## Honest unknowns

Things the spec doesn't resolve and why.

## Questions for Brock

Points where Brock's context would resolve an ambiguity or calibration.
```

Target length: 2000–4000 words of actual spec content, plus the AD draft. Denser is better. Over 5000 words means it's padded.

### 7. Register and close

```bash
cd /Users/brock/Documents/GitHub/seldon/
seldon cc complete cc_tasks/2026-04-18_cc5_sleep_function_architecture.md
```

Close spec ResearchTask `de84cb6a`.

Commit:

```bash
git add docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md
git add cc_tasks/2026-04-18_cc5_sleep_function_architecture.md
git commit -m "cc5: Wintermute sleep-function architecture spec + AD-023 draft"
```

---

## Success Contract

**Deliverables:**
1. `docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md` exists.
2. All three sleep functions fully spec'd per template (every field filled, no placeholders).
3. Literature scan has 5–8 references with applicability notes.
4. Cross-cutting concerns section covers ordering, event sourcing, arbitration, and SPOF resistance explicitly.
5. Dashboard metrics table has at least the 8 metrics listed in Step 4.
6. AD-023 draft included at end of doc.
7. CC task file marked complete in graph; spec ResearchTask `de84cb6a` transitioned to `completed`.
8. Git commit exists.

**Verification commands:**
```bash
# Deliverable exists
ls -la /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md

# All three sleep functions have spec sections
grep -cE '^## Sleep Function [ABC]' /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md
# Expect: 3

# Each sleep function section contains all required subsection headers
# (Purpose, Trigger, Input, Process, Output, Compute budget, Failure modes, Measurement)
# Manual check — these may be bolded lines rather than headers

# AD-023 draft present
grep -c 'AD-023 Draft' /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md
# Expect: >= 1

# Dashboard metrics table
grep -cE 'sleep\.(collapse|split|edge|arbitration|compute)\.' /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md
# Expect: >= 8 distinct metric references

# Seldon verify
cd /Users/brock/Documents/GitHub/seldon/
seldon verify --quiet && echo OK || echo FAIL
```

**Scope boundaries (DO NOT do these):**
- Do NOT write implementation code. This is design only.
- Do NOT modify Wintermute. No touching `/Users/brock/Documents/GitHub/wintermute/` or `~/.wintermute/` if either exists.
- Do NOT pick Option A vs Option B from CC1 Q4 (claude-mem adopt-vs-extract). That's Phase C's call. The spec should work under either option — name where it's option-dependent if so.
- Do NOT specify a full Bayesian belief propagation system unless the literature scan argues clearly for it (it probably won't). The working hypothesis is AI-proposed-with-human-arbitration. Label it accurately.
- Do NOT pad. 2000–4000 words of actual spec. If you hit 5000+, cut.
- Do NOT commit an AD file at `docs/design/AD-023_*.md`. The draft lives inside the CC5 deliverable until Phase C promotes it (or not). Premature commitment is the anti-pattern.
- Do NOT design v2 / v3 features. V1 is: three sleep functions running on nightly cadence, producing proposals for human arbitration, observable via dashboard. Anything beyond is explicitly deferred.
- Do NOT specify ensemble multi-provider LLM dispatch as v1 requirement. Name it as v2, move on.

**Assumptions:**
- Wintermute graph is Neo4j at `bolt://localhost:7687`, separate database per AD-004 (per-project isolation).
- LLM for sleep-function reasoning is Gemini Flash as baseline (cost + quality tradeoff per prior Wintermute decisions). Local orchestration via Hermes-3 possible per LeStat plan but not required for v1.
- Event sourcing pattern matches Seldon's (JSONL append-only log).
- Arbitration happens asynchronously — user reviews when they want. System tolerates queue size.
- sift-kg's three-layer pattern is the reference architecture for collapse. If the spec deviates, explain why.

---

## What this feeds into

- **Phase C synthesis**: decides whether AD-023 gets promoted, whether sleep functions go in the 75% (high-ROI shippable) or 15% (long-lead solid-value) bucket, whether any part gets deferred.
- **CC4 dashboard unblock**: the metrics table here is the spec for Q-a's curation panel. Implementation waits for sleep-function code, but the dashboard can reserve the panel.
- **Future Wintermute initialization**: when Wintermute becomes Seldon-managed, this spec migrates and becomes the implementation roadmap.
- **Candidate AD-022 (CLI-default)**: the arbitration workflow here is a data point — is it CLI or something else? If CLI, it's evidence for AD-022.
- **Candidate AD-024 (Observability)**: sleep functions are the highest-signal thing Wintermute will do. The measurement requirements here inform what "observable by default" means for the project.

If this spec is wrong, the next year of Wintermute work is wrong. Be honest about uncertainty. A spec that says "we don't know yet, here's what we'd need to find out" is better than a spec that pretends.

---

*End of CC5 task spec.*
