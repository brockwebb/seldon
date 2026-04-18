# AD-019: Agentic Content Audit Pipeline

**Date:** 2026-04-01
**Status:** Design
**Depends on:** AD-014 (agent roles as graph artifacts), AD-016 (paper QC severity tiers), AD-018 (document structure graph)
**Motivated by:** Repeated audit process failures on ai4stats book (chapters 1-6 shipped with zero inline citations); manual audit process that worked but didn't survive transfer to tooling; `seldon paper audit` doing Tier 2/3 prose QC only, not substantive content verification.

---

## 1. Problem Statement

The current Seldon paper tooling has a massive gap between what `seldon paper audit` does (prose quality checks — sentence length, banned words, style violations) and what a proper content audit requires (claim verification, citation coverage, content depth assessment, factual accuracy). This gap was invisible as long as Brock performed audits manually with a rigorous mental checklist. The moment the process was offloaded to tooling, it degraded because none of the tools do what the manual process did.

The manual audit process that worked on ai4stats (documented in the Chapter 3 audit hotwash) had four capabilities:

1. **Claim classification** — every assertion tagged as verifiable fact, engineering judgment, or conjecture
2. **Citation verification** — dual-path search (web + Perplexity) for every factual claim
3. **Content depth assessment** — distinguishing substantive sections from outline-grade material that got lightly fleshed out
4. **Action routing** — unsourced facts auto-generate search tasks (don't bother the author); structural decisions get flagged for design sessions (do bother the author)

None of these exist in Seldon today. `seldon paper audit` handles AD-016 tier checks. This AD defines the complementary system: a content-level audit pipeline that produces typed, routed findings as Issue artifacts in the graph.

---

## 2. Design Principles

**The audit produces typed outputs, not prose reports.**

An unsourced factual claim doesn't need the author's judgment — it needs a search task. A thin section needs a design decision. A terminology inconsistency needs a glossary check. The audit pipeline classifies findings and routes them to the correct downstream workflow without requiring the author to manually triage every finding.

**Findings are Issues, not warnings.**

Every audit finding becomes an Issue artifact (already defined in `research.yaml`) with `affects` edges to the audited PaperSection. Issues are typed, prioritized via the Eisenhower grid, and resolvable via `resolved_by` edges to ResearchTask artifacts. This means audit findings are tracked, stateful, and queryable — not a prose report that gets read once and forgotten.

**Cross-section impacts are tracked from day one.**

If an audit finding in Section 3 implies something is wrong or needs checking in Section 7, that is not a "future enhancement." It is a ResearchTask created immediately, linked to the affected section, and visible in `seldon briefing`. Ignoring cross-section impacts at audit time is how drift compounds into a mess that costs 10x to unwind. The graph exists to prevent exactly this. Use it.

---

## 3. Claim Classification Taxonomy

Every assertion in audited prose is classified into one of three categories. This classification drives the routing logic.

| Category | Definition | Routing |
|----------|-----------|---------|
| **Fact** | A verifiable empirical claim: numbers, dates, comparative statements, attributions of findings to specific researchers, descriptions of how methods work. Can be checked against external sources. | If uncited → auto-generate verification task |
| **Judgment** | An evaluative statement grounded in the author's expertise or the field's consensus: "X is preferable to Y for this use case," "this approach is well-suited for federal workflows." Not falsifiable by a single source, but should be framed as judgment, not fact. | If stated as fact → flag for reframing. If unsupported → flag for evidence or explicit framing as author judgment |
| **Conjecture** | A speculative or forward-looking claim: "this may enable," "future work could," "we hypothesize that." Appropriate in discussion sections; inappropriate in methods or results. | If in methods/results → flag for promotion (find evidence) or deletion. If in discussion → acceptable if framed appropriately |

This taxonomy is deliberately simple. Three categories, clear routing rules, no ambiguity about which bin something falls into. If it can be wrong, it's a fact. If it's an opinion backed by expertise, it's a judgment. If it's speculation, it's conjecture.

The taxonomy is embedded in the audit agent's prompt, not in the schema. No schema changes needed. If experience reveals a fourth category is required, add it to the prompt and document the change in this AD.

---

## 4. Audit Pipeline

### 4.1 Input

A PaperSection artifact ID, a chapter file path, or a batch directive ("audit all sections in state `draft`").

### 4.2 Processing Stages

**Stage 1: Paragraph-level claim extraction**

A CC subagent reads the section and produces structured output: for each substantive paragraph, a list of assertions with their classification (fact/judgment/conjecture) and the specific text span.

Output format (structured, not prose):
```yaml
- paragraph: 3
  assertions:
    - text: "Traditional NLP methods like bag-of-words achieve lower accuracy on open-ended survey responses"
      classification: fact
      citation_present: false
      existing_citation: null
    - text: "LLMs are better suited for this task because they capture contextual meaning"
      classification: judgment
      citation_present: false
      existing_citation: null
    - text: "Fine-tuning costs have dropped 10x since 2024"
      classification: fact
      citation_present: false
      existing_citation: null
```

**Stage 2: Coverage check**

For each fact-classified assertion:
- Check if the paragraph's PaperSection has `cites` edges to Citation or Result artifacts that plausibly cover the claim
- Check if an inline citation is present in the prose text (regex for author-year patterns, `{cite}` directives)
- If neither: classify as `citation_gap`

For each judgment-classified assertion:
- Check if framed as judgment ("we recommend," "in our experience," "the field generally considers") or stated as fact
- If stated as fact: classify as `unsupported_claim`

For each conjecture-classified assertion:
- Check section type (methods/results vs. discussion/future work)
- If in methods/results: classify as `unsupported_claim` with note "conjecture in empirical section"

**Stage 3: Content depth assessment**

Per section, compute:
- Word count
- Ratio of specific claims (with evidence/citations) to general statements
- Presence of examples, case studies, or worked demonstrations
- Comparison to sibling sections at same depth (are peer sections substantially longer/more detailed?)

If a section falls below thresholds on multiple metrics: classify as `missing_content` (outline-grade material needing expansion or explicit scoping as secondary).

**Stage 4: Cross-section impact identification**

For every finding, the auditor must consider: does resolving this finding affect any other section? This is not optional and not a future enhancement.

Examples of cross-section impact:
- A terminology inconsistency here means the same term may be wrong in other sections that use it
- A factual correction here may contradict a claim made in a different section
- A concept introduced here is referenced downstream — changing it cascades
- A citation gap here may also be a citation gap in another section that makes the same claim

For each cross-section impact:
- Identify the affected section (by name, artifact ID, or file path)
- State why it's affected
- State what kind of audit the affected section needs (terminology check, factual consistency check, citation check, or full audit)
- Assign priority (high if the impact could introduce an error; medium if it's consistency maintenance; low if it's a style/framing concern)

These become ResearchTask artifacts linked to the affected PaperSection via `blocks` edges. They show up in `seldon briefing` and cannot be forgotten.

**Stage 5: Issue creation and routing**

Each finding becomes an Issue artifact with:
- `issue_type`: mapped from the finding type (see §5)
- `importance` / `urgency`: assigned by routing rules (see §5)
- `detection_method`: `automated_check`
- `target`: `citation`, `content`, `terminology`, or `structure`
- `affects` edge: to the PaperSection artifact
- `description`: the specific finding with enough context to act on

Each cross-section impact becomes a ResearchTask artifact with:
- `description`: what needs checking in the downstream section and why
- `blocks` edge: to the affected PaperSection
- `depends_on` edge: to the Issue that triggered it (provenance)

### 4.3 Output

1. **Issue artifacts in the graph** — queryable via `seldon issue list`, surfaced in `seldon briefing`
2. **ResearchTask artifacts for cascading audits** — tracked in the graph, surfaced in `seldon briefing`, linked to source findings
3. **Verification task file** — a CC task in `cc_tasks/` containing pre-formatted Perplexity queries for all `citation_gap` findings. One task file per audit batch, not per finding.
4. **Audit summary** — printed to terminal: counts by issue type, sections flagged, cascading tasks created, coverage statistics. Not a prose report — a structured summary.

---

## 5. Finding-to-Issue Routing Rules

| Finding | Issue Type | Importance | Urgency | Target | Action |
|---------|-----------|------------|---------|--------|--------|
| Fact without citation | `citation_gap` | high | high | citation | Auto-generate Perplexity query |
| Fact with citation but unverified claim | `unsupported_claim` | high | medium | citation | Auto-generate Perplexity verification query |
| Judgment stated as fact | `unsupported_claim` | medium | medium | content | Flag for reframing (needs author) |
| Conjecture in empirical section | `unsupported_claim` | high | high | content | Flag for promotion or deletion (needs author) |
| Terminology not matching ontology | `terminology_inconsistency` | high | high | terminology | Auto-generate glossary fix task |
| Section below depth thresholds | `missing_content` | medium | low | content | Flag for design session (needs author) |
| Stale cross-reference | `stale_content` | high | high | structure | Auto-generate fix task |
| Internal contradiction with other section | `internal_contradiction` | high | high | content | Flag for resolution (needs author) |
| Cross-section impact identified | — | per finding | per finding | — | Create ResearchTask for downstream section audit |

**Routing principle:** If the fix doesn't require the author's judgment, auto-generate the task and don't bother the author. If it does require judgment, flag it with enough context for the author to make the decision quickly. If it affects another section, create a tracked task for that section regardless — drift prevention is non-negotiable.

---

## 6. Cross-Section Propagation Model

### 6.1 The Problem

Auditing sections in isolation creates a false sense of completeness. If Section 3 introduces a concept that Section 7 builds on, and the audit of Section 3 reveals the concept needs reframing, Section 7 is now silently wrong. Without tracking this, the author discovers it weeks later during a read-through and has to do forensic archaeology to figure out what changed and when.

### 6.2 Phase 1-2: Sequential with Tracked Tasks

In the initial implementation, audits run one section at a time. For each finding with cross-section impact, the auditor creates a ResearchTask:

```
ResearchTask: "Audit Section 07 (Operationalization) — terminology_check triggered by 
  finding in Section 03 audit: term 'context buffer' replaced with 'context window'. 
  Verify Section 07 uses canonical terminology."
  → blocks: PaperSection(section_07)
  → depends_on: Issue(terminology_inconsistency in section_03)
```

The task shows up in `seldon briefing`. When the author (or a CC session) next works on Section 07, the task is visible. The downstream audit runs as a separate invocation, which may itself generate further cascading tasks.

**Cascade depth limit:** To prevent runaway cascading, set a maximum cascade depth of 3. If a cascading audit of Section 7 triggers a cascade to Section 12, which triggers a cascade to Section 3 (the original), the cycle is detected and flagged for author review rather than creating infinite tasks. The graph structure makes cycle detection trivial.

### 6.3 Phase 3+: Multi-Agent Parallel Audit

When the data from Phase 1-2 shows that:
- Cascading tasks are frequent (most audits generate 2+ downstream tasks)
- Sequential execution is too slow (cascaded findings become stale before the downstream audit runs)
- Coordination failures occur (two sequential audits make conflicting recommendations about the same section)

Then the architecture evolves to parallel multi-agent audit:

- One auditor agent per section, running concurrently
- A coordinator agent that receives findings from all auditors, detects conflicts, and resolves contradictions before any changes are made
- The coordinator uses `seldon paper impact` to compute full blast radius before approving any finding that touches shared concepts
- Maximum concurrent agents configurable (default: number of sections being audited, cap at a reasonable limit TBD from experience)

This is architecturally consistent with the CC agent swarm model (AD-014) — the coordinator is the Lead role, auditor agents are Workers. The graph mediates state so agents don't need direct communication beyond the coordinator.

**This is not built in Phase 1.** But the output format, the ResearchTask propagation model, and the cascade tracking are designed from day one to support this evolution. The Phase 1 sequential model is a degenerate case of the multi-agent model (one agent, no coordinator), not a separate architecture that gets thrown away.

---

## 7. Relationship to Existing Systems

### AD-016 (Paper QC Severity Tiers)

AD-016 handles **prose quality**: sentence length, banned words, style violations, formatting. This is syntactic QC.

AD-019 handles **content quality**: are the claims correct, cited, and appropriately framed? This is semantic QC.

They are complementary, not overlapping. `seldon paper audit` runs AD-016 checks. The new audit pipeline (command TBD — likely `seldon paper audit --content` or `seldon audit`) runs AD-019 checks. Both produce Issues, but in different `issue_type` categories.

### AD-014 (Agent Roles)

The content audit pipeline requires a new agent role: **Auditor**. This role has a specialized retrieval profile (needs the section text, the ontology, the citation graph, sibling section metadata, and cross-reference edges for blast radius) and a specialized system prompt (the claim classification taxonomy and routing rules from this AD).

The Auditor role is registered as an AgentRole artifact in the graph per AD-014. Its system prompt contains the claim classification taxonomy, the routing rules, the cross-section impact protocol, and the output format specification. The role is invoked via CC Task tool dispatch, consistent with existing workflow patterns.

The Phase 3+ coordinator role will be a separate AgentRole artifact when that phase is implemented.

### AD-018 (Document Structure Graph)

The audit pipeline depends on document structure to determine section depth, sibling sections for comparative depth assessment, parent-child relationships for cross-reference validation, and cross-section edges for blast radius computation. AD-018 provides this.

### `seldon paper impact`

The existing impact command computes blast radius from the graph — what's affected if a given artifact changes. The audit pipeline uses this in two ways:
1. The auditor consults impact data when identifying cross-section impacts (Stage 4)
2. The Phase 3+ coordinator uses it to compute full blast radius before approving changes

### DAAF Patterns (Extracted, Not Adopted)

From the DAAF analysis (2026-02-22), the following patterns are incorporated:

1. **Interleaved QA** — audit runs per-section, immediately after writing, not batched at project end. The audit is part of the section completion workflow, not a separate phase.
2. **Autonomous deviation rules** — findings that don't need author judgment are auto-routed to tasks. Findings that need judgment STOP and escalate. Encoded in the routing table (§5), not in prose instructions.
3. **Skill vs. agent separation** — the claim classification taxonomy is knowledge (could become a Seldon skill); the audit agent role is behavior. Kept separate per DAAF's pattern.

---

## 8. Implementation Approach

### Phase 1: Manual-assist audit with cascading tasks (immediate, no new Seldon code)

Build reusable audit infrastructure into Seldon: auditor agent role, system prompt, output format spec, CC task template. Any project invokes the template. Cascading tasks are created manually via `seldon task create` per the auditor output.

This validates the taxonomy, routing rules, and cross-section propagation model on real content before investing in automation.

### Phase 2: `seldon audit` CLI command

Automate Issue creation and ResearchTask creation from structured findings. The CC agent still does the classification (it requires LLM reasoning), but Issue creation, edge creation, cascading task creation, and verification task file generation are automated via CLI.

```
seldon audit <section_id_or_path>     # audit one section
seldon audit --state draft            # audit all sections in draft state
seldon audit --batch                  # audit all sections, one pass
seldon audit --cascade-depth 3        # max cascade depth (default 3)
```

Output: Issues created in graph, ResearchTasks for cascading audits, verification task file in `cc_tasks/`, summary to terminal.

### Phase 3: Multi-agent parallel audit

When Phase 2 data shows cascading is frequent and sequential is too slow, implement the coordinator + parallel auditor model described in §6.3. The coordinator agent role is registered per AD-014. The workflow is updated to support concurrent execution with conflict detection.

### Phase 4: Integration with section state machine

Add `audited` as a prerequisite for PaperSection state transition from `draft` → `review`. A section cannot enter `review` state until the audit has run and all Critical-routed findings are resolved (or explicitly waived with rationale). Cascading audit tasks for the section must also be resolved.

This is optional and should be evaluated after Phase 2 produces enough data to know whether the gate adds value or just friction.

---

## 9. What This Does NOT Do

- **Does not replace human judgment on argument coherence.** The audit checks claims, not reasoning. Whether the conclusion follows from the evidence is a human assessment.
- **Does not verify citations are correct.** It identifies missing citations and generates verification queries. Verification itself is external (Perplexity, web search, library lookup).
- **Does not enforce a citation style.** APA formatting, BibTeX correctness, etc. are separate concerns.
- **Does not do prose quality checks.** That's AD-016 / `seldon paper audit`. Different tool, different concern.
- **Does not require an API key for the audit agent.** Phase 1-2 run via CC tasks using the existing Claude Code subscription. No additional API costs.
- **Does not audit downstream sections automatically in Phase 1-2.** It creates tracked tasks for them. The downstream audit is a separate invocation. Phase 3+ may automate this with multi-agent coordination.

---

## 10. Documentation Ratio Fix (Related but Separate)

This AD also addresses the documentation ratio noise problem reported by `seldon go`. The fix is a property category split:

**Current state:** All non-required properties are `category: documentation`. Auto-populated fields (content_hash, sequence, depth, epoch) count the same as human-authored fields (interpretation, methodology_note).

**Fix:** Add `category: system` to `PropertyDef`. Properties that are auto-populated by Seldon commands (`paper sync`, `ontology ingest`, etc.) are reclassified as `system`. `run_docs_check` reports two numbers:
- System completeness (should be ~100% — indicates sync commands are working)
- Documentation completeness (human-authored context — the number you care about)

`seldon go` reports only documentation completeness. System completeness is reported only if it drops below 100% (indicating a sync bug, not a documentation gap).

**Properties to reclassify as `system`:**
- PaperSection: `file_path`, `content_hash`, `sequence`, `depth`, `section_type`
- OntologyTerm: `namespace`, `inheritance`, `content_hash`, `epoch`
- Figure: `figure_number`
- Table: `table_number`

This is a schema change to `research.yaml` + code change to `loader.py` and `docs.py`. Scoped as a CC task, not part of the audit pipeline implementation.

---

## 11. Open Questions

1. **Depth thresholds for Stage 3.** What word count / specificity ratio distinguishes "substantive" from "outline-grade"? Needs calibration from real data. Start with heuristic (< 500 words AND < 30% specific claims = flag), adjust.

2. **Batch vs. incremental audit.** Should the audit run on the full section every time, or track which paragraphs changed since last audit and only re-classify those? Incremental is more efficient but risks missing context-dependent classification changes. Start with full-section, optimize later if performance matters.

3. **Integration with `seldon verify`.** Should `seldon verify` include a lightweight audit check (e.g., "sections in `review` state with zero citation edges")? Possibly, but `seldon verify` is currently a fast integrity gate. Adding LLM-dependent checks would slow it down. Keep them separate unless a non-LLM heuristic is sufficient.

4. **Multi-agent coordination protocol.** When Phase 3 arrives, how do parallel auditors communicate conflicts? Through the graph (each writes findings, coordinator reads all) or through direct messaging? Graph-mediated is simpler and consistent with Seldon's architecture. Direct messaging adds complexity. Defer decision to Phase 3 design session.

5. **Cascade depth limit.** Default of 3 is a guess. Too low and real cascades get truncated. Too high and cycles cause noise. Calibrate from Phase 2 data.

---

## 12. References

- DAAF framework analysis: Claude chat 2026-02-22 (https://claude.ai/chat/72a92667-bed3-4b69-81d6-ea2e404817d0)
- RWA evaluation: Claude chat 2026-03-31 (https://claude.ai/chat/c95184fa-6348-4477-905c-110e0f583104)
- ai4stats Chapter 3 audit hotwash: Claude chat 2026-04-01 (in-session)
- AD-014: Agent Roles as Graph Artifacts
- AD-016: Paper QC Severity Tiers
- AD-018: Document Structure Graph
- Citation remediation audit process: Claude chat 2026-03-27 (https://claude.ai/chat/3c5f9714-7d07-45a0-91df-6f3e94a115fe)
