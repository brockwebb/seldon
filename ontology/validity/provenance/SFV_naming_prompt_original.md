# Naming Help: A New Validity Type for LLM-Based Research Pipelines

## What I'm describing

When you use LLMs for multi-step research (not single-shot Q&A, but sustained work across turns, sessions, and sometimes multiple models), the system accumulates internal state: decisions made, terminology established, intermediate findings, methodological choices. This accumulated state becomes the foundation that all subsequent steps build on.

The problem is that this internal state degrades in ways that have no parallel in traditional research instruments. Specifically:

- **Terminology drift:** The model subtly changes terms for the same concept across a long session, and the drifted terms get treated as canonical.
- **Confabulation as memory:** The model "remembers" something that was never established and acts on it as if it were agreed-upon context.
- **Compaction loss:** Context window management (summarization, truncation) silently strips nuance from earlier decisions, changing their meaning.
- **Stale context:** Earlier information gets superseded by later decisions, but the earlier version persists in the window and influences outputs.
- **Session boundary loss:** Starting a new thread drops everything not explicitly carried forward. The system acts as if prior work didn't happen.

These are NOT the same as hallucination in the usual sense. These are failures of the system to maintain fidelity to its own accumulated working state over time.

## Why existing validity types don't cover this

The four classical validity types (construct, internal, external, statistical conclusion) all assume the measurement instrument is stable. A survey doesn't forget its skip logic mid-interview. A regression model doesn't rename variables between iterations.

There IS an existing concept called "context validity" in psychometrics, but it addresses something different: whether a measure remains valid when you change the external conditions (population, setting, culture). That's about the environment AROUND a fixed instrument.

What I'm describing is about the state WITHIN the instrument's execution. The instrument itself is not fixed. Its internal context is dynamic and degrades.

## What I need a name for

A validity type that captures: **the degree to which an AI-assisted research pipeline maintains fidelity to its own accumulated state (decisions, terminology, findings, methodology) across the full arc of its execution, such that outputs at step N are grounded in what was actually established at steps 1 through N-1, rather than in drifted, confabulated, compacted, or lost versions of that state.**

## Options I've considered

- **Operational Context Validity** (distinguishes from traditional "context validity" by specifying it's about operational/execution state rather than external conditions)
- **Execution Fidelity Validity**
- **State Coherence Validity**
- **Pipeline Integrity Validity**
- **Temporal State Validity**

## Constraints on the name

- Must not collide with or be easily confused with existing validity types (construct, internal, external, statistical conclusion, content, ecological, face)
- Must not collide with the existing "context validity" concept in psychometrics (external conditions)
- Should be intuitive enough that a methodologist hearing it for the first time gets the gist
- Should work in both academic writing and practitioner communication
- This will be used in a federal statistics / AI governance context, so it needs to sound rigorous, not trendy

## What I'm asking

1. Is there an existing term in any field that already covers this concept precisely?
2. If not, which of my candidate names works best, or do you have a better suggestion?
3. Any concerns with the framing that I should address before publishing?
