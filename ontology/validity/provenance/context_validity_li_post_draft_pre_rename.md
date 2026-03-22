LINKEDIN POST — Context Validity
Draft: 2026-03-21
---

When we use AI systems for research, we inherit four classical validity types from methodology: construct, internal, external, and statistical conclusion validity.

None of them address what actually goes wrong.

What goes wrong is this: the context drifts. The AI invents terminology that was never established. Compaction silently rewrites earlier decisions. Session boundaries drop critical information. The system acts on a corrupted version of what was agreed upon three turns ago, and nobody notices because it sounds fluent.

I am calling this Context Validity: the degree to which the information a system acts on at step N is a faithful representation of what was established at steps 1 through N-1.

Threats to context validity include:
- Terminology drift (the model subtly changes terms across a long session)
- Confabulation as memory (the model "remembers" something never established)
- Compaction loss (context window management silently strips nuance)
- Stale context (earlier information superseded by later decisions but still present)
- Session boundary loss (thread death drops everything not explicitly carried forward)

This is not a theoretical concern. Anyone who has worked with LLMs on a multi-session research project has experienced context validity failures. The difference is whether you engineered against them or just hoped for the best.

I have been building systems (config-driven ontologies, graph-backed vocabulary, validation loops) specifically to maintain context validity in AI-assisted federal research. A more detailed treatment is forthcoming. But the core claim is simple: if you cannot demonstrate that your AI pipeline maintained context fidelity across its full execution, your findings are built on a foundation you cannot verify.

The four classical validity types assume a stable measurement instrument. An LLM is not a stable instrument. Context Validity is the missing piece.

#AI #ResearchMethodology #FederalStatistics #AIGovernance
