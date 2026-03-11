# Agent Tool Design Lessons — Applied to Seldon

**Date:** 2026-03-01  
**Status:** Reference — Design principles derived from Anthropic's Claude Code tool evolution  
**Source:** Anthropic engineering post "Lessons from Building Claude Code: Seeing Like an Agent" (Thariq, 2026), analyzed against Seldon architectural decisions.

---

## 1. The Tool Budget Is Real (~20 Commands Max)

Claude Code operates with roughly 20 tools. Beyond that threshold, model performance degrades: wrong tool selection, hallucinated tool names, confused parameter usage. This isn't a soft guideline — it's a cognitive ceiling for the model invoking the tools.

**Seldon implication (T0-3 CLI spec):** Count the distinct CLI commands. The planned command groups (`seldon artifact`, `seldon link`, `seldon result`, `seldon task`, `seldon session`) must stay within this budget. If the total exceeds ~20 distinct invocable commands, consolidate. This reinforces AD-003's decision to use CLI over MCP — fewer, clearer tools beat a sprawling tool surface.

**Action:** During T0-3, enumerate all planned commands and verify count stays under 20. If over, merge or defer.

---

## 2. One Tool, One Job — No Overloading

Anthropic's elicitation feature took three attempts. Attempt one overloaded an existing tool (ExitPlanTool) with a second purpose — the model couldn't disambiguate. Attempt two used a custom markdown format — the model couldn't follow formatting rules. Attempt three was a dedicated single-purpose tool (AskUserQuestion). Simplest won.

**Seldon implication:** Each CLI command must have unambiguous semantics when described as a tool definition. Don't overload `seldon artifact update` to handle state transitions AND metadata changes AND relationship updates. The model calling these commands needs to reason clearly about what each one does.

**Design test:** Write each command's description as a one-sentence tool definition. If you can't describe it in one sentence without "and," it's doing too much.

---

## 3. Surface State, Don't Prescribe Action

Claude Code's TodoWrite tool worked for weaker models but became a liability with stronger ones. The rigid checklist prevented the model from adapting when context changed mid-task. The replacement (Task tool) provides coordination state without prescribing sequence.

**Seldon implication (AD-007, T2-5 session briefing):** `seldon briefing` should surface current state — open tasks, stale results, incomplete provenance chains, recently changed artifacts — without prescribing what to do about them. The briefing is a status report, not a work order. Let the human or model decide priority and sequence based on session intent.

**Anti-pattern to avoid:** "You should next: 1) fix stale result X, 2) complete task Y, 3) update section Z." Instead: "3 open tasks (1 blocking), 2 stale results, 1 incomplete provenance chain."

---

## 4. Search Over Pre-Loading (Progressive Disclosure)

Claude Code replaced RAG (pre-loaded context) with grep (model-driven search). Models that find their own context understand it more deeply than models that receive pre-chewed summaries. The winning pattern is progressive disclosure: provide layers of information the model can pull on demand.

**Seldon implication (AD-005 general_retrieve):** The `general_retrieve()` interface should not dump everything into context. It should be a focused retrieval tuned to what the current session needs. This validates the ALMA-inspired design: different retrieval profiles for different roles/contexts. Session briefings should be compact summaries with the ability to drill deeper on demand, not exhaustive context loads.

**Practical pattern:** `seldon briefing` returns a summary. `seldon briefing --detail tasks` or `seldon result trace <id>` provides depth. The model chooses when to go deeper.

---

## 5. Tools Must Evolve With Model Capabilities

TodoWrite helped weak models stay on track but constrained strong models. The tool lifecycle is: build for current model → model improves → tool becomes constraint → redesign tool. This is normal, not failure.

**Seldon implication:** Design for the current Claude capability but don't over-engineer scaffolding that assumes the model needs hand-holding. The authority model (AD default: auto-accept) is already aligned with this — trust the model, human intervenes at decision points. As models improve, Seldon's command surface should simplify, not grow.

**Practical:** Avoid building elaborate multi-step workflows into the CLI that assume the model can't plan. Provide atomic operations and let the model compose them.

---

## 6. What Does NOT Apply to Seldon

**RAG-is-dead narrative:** RAG failed for codebase navigation where structural exploration matters. Seldon's use case is different — structured graph retrieval over typed artifacts with known relationships. Graph queries are not vector similarity searches. Don't conflate the two. Wintermute's Neo4j + LightRAG architecture serves a fundamentally different retrieval need than grepping a codebase.

**Subagent pattern:** Claude Code's Guide subagent is interesting but premature for Seldon. The specialist retrieval profiles (PL-003) already capture this concept more cleanly at the architecture level. Don't add subagent complexity before Phase 1 is running.

---

## 7. Summary Checklist for T0-3 (CLI Spec Design)

- [ ] Total distinct commands ≤ 20
- [ ] Each command describable in one sentence without "and"
- [ ] Command names are unambiguous action-object pairs (e.g., `result register`, `task create`)
- [ ] Briefing outputs state, not prescriptions
- [ ] Retrieval supports progressive disclosure (summary → detail on demand)
- [ ] No multi-purpose command overloading
- [ ] Command descriptions written as tool definitions a model would reason about

---

## References

- Anthropic. "Lessons from Building Claude Code: Seeing Like an Agent." (2026)
- Seldon AD-003: CLI Commands, Not MCP Servers
- Seldon AD-005: Standard Interface Contract (update/retrieve)
- Seldon AD-007: Task Completion Tracking as First-Class Artifact Type
- Seldon T0-3: CLI command design (project plan)
