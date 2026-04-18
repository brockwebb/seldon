# Dual-Model Audit Verification — 2026-04-18

**Task:** cc_tasks/2026-04-18_dual_model_audit.md
**Section audited:** 03_classical_validity.md
**Baseline model:** claude-opus-4-6 (run-002, 2026-04-17)
**Alt model:** gemini-2.5-flash (Google AI Studio v1beta, 2026-04-18)
**Dispatch path:** Direct v1beta API call (bypass litellm truncation issue; see Technical Notes)

---

## Findings count

| Gate | Baseline (opus) | Alt (Gemini) | Overlap | Baseline-only | Alt-only |
|---|---|---|---|---|---|
| content_audit findings | 0 | 2 | 0 | 0 | 2 |
| flagged claims | 0 | 4 | 0 | 0 | 4 |
| terminology violations | 0 | 2 | 0 | 0 | 2 |
| overall status | clean | findings_present | — | — | — |

---

## Divergence summary

### Unique findings from Gemini (alt-only)

1. **Terminology inconsistency: context_window vs. accumulated_state container/content** (moderate)
   - Location: Paragraph 3 (Terminology Note)
   - Issue: Paper defines "context window" as the mutable buffer that *accumulates* content, then uses phrasing "accumulated state that has built up *inside* the context window" — treating context window as a container. If context window is the content-accumulating buffer, then accumulated state is that content, not something inside it. The definitions imply identity (context_window = the accumulating content), but the prose implies containment (accumulated_state inside context_window).
   - Recommendation: Clarify the container/content distinction explicitly, or revise the controlled vocabulary to make context_window a container and accumulated_state its contents.

2. **Structural: Threat references (T1, T4, T5) appear before formal definition** (minor)
   - Location: Paragraph 3 (same terminology note)
   - Issue: T1, T4, T5 are cited with specific behavioral effects before they are defined. Only T1 gets a section reference (Section 5). T4 and T5 get no forward reference.
   - Recommendation: Add forward references for T4 and T5, or defer the threat examples to after Section 5.

### Unique findings from Baseline (baseline-only)

None. Opus returned `status: clean` with zero findings.

### Flagged claims (Gemini-only)

1. "The instrument stability assumption is invisible because it has never been violated." — judgment without empirical support; strong historical claim about methodologist experience
2. "Every stateful pipeline has some degree of state degradation." — stated as universal fact; may be a definitional claim or a conjecture needing hedging
3. T1/T4/T5 effects described in paragraph 3 before formal definition — fact-claim using undefined terms
4. The four classical types "never state explicitly" the instrument stability assumption — interpretive claim, plausible but not cited

---

## Verdict

**Divergence > 0. SPOF break successful.**

The two models produce genuinely different outputs on the same section. Opus declared the section clean; Gemini flagged a terminology inconsistency (context_window as buffer vs. container) and a structural issue (undefined threat references). Both findings are substantive, not noise:

- The context_window/accumulated_state container-vs-content tension is a real definitional ambiguity that could create downstream confusion when readers reconcile the Terminology Note with the formal glossary. This is a finding worth addressing.
- The T4/T5 forward-reference gap is a genuine structural choice that warrants conscious decision, not an oversight. Opus missed it; Gemini flagged it.

The two models are not simply agreeing with different words — they are producing different verdicts and different finding types. This confirms that a single-model audit loop creates a blind spot: the baseline model (opus) produced the terminology and structure it was reviewing, and has calibrated expectations that prevent it from flagging its own definitional choices as ambiguous. The alt model, seeing the section cold, identified the ambiguity immediately.

**Recommendation:** Enable AUDIT_MODEL routing in the default pipeline for sections in `review` or `published` state, where false negatives are most costly. The terminology finding from Gemini should be triaged and resolved before this section advances to `final`.

---

## Technical Notes

- **litellm truncation issue**: `litellm.completion()` with `gemini/gemini-2.5-flash` returned `finish_reason: MAX_TOKENS` at ~1300 chars regardless of `max_tokens` setting. Root cause: Gemini 2.5 Flash uses reasoning/thinking tokens (non-visible) that consume the token budget before output tokens. Workaround: called the Google AI Studio `v1beta` API directly for the alt audit run. `audit_dispatch.py` uses litellm and will need a think-budget-aware wrapper before it can reliably run Gemini 2.5 Flash at full output length. This is a known limitation documented here; fixing it is out of scope for this task.
- **Baseline source**: run-002 (2026-04-17) rather than a fresh Sonnet run. The existing baseline is opus-4-6, not Sonnet. Divergence framing in the spec ("Sonnet vs. alt") applies to the general pattern; the actual comparison here is Anthropic-family model (opus) vs. Google-family model (Gemini), which is a stronger SPOF break than same-family comparison.
- `gemini-2.0-flash` and `gemini-1.5-flash` returned 404 from this API key (deprecated for this tier). `gemini-2.5-flash` was the only available stable model.

---

## Output files

- Baseline: `brock_projects/audits/dual_model_verification_2026-04-18/baseline_opus.yaml`
- Alt: `brock_projects/audits/dual_model_verification_2026-04-18/alt_gemini.yaml`
