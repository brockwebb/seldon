# AD-016: Paper QC Severity Tiers — Critical / Substantive / Administrative

**Date:** 2026-03-20
**Status:** Finalized
**Scope:** Paper QC system (`seldon paper audit`, `seldon paper build`)

---

## Decision

Replace the current two-file Tier 2 / Tier 3 classification with three semantically distinct tiers — **Critical**, **Substantive**, and **Administrative** — each with different build behavior. All rules live in a single per-project `paper/paper_qc_config.yaml` (no global defaults yet). Administrative rules use explicit budgets rather than binary bans.

---

## Rationale

The current tier model conflates severity levels that require different responses:

- **Tier 2** (`paper_qc_config.yaml`) groups `max_sentence_words` (readability preference) with `figures_have_captions` (publication requirement). One is advisory; the other is a hard dependency.
- **Tier 3** (`paper_style_config.yaml`) groups `banned_phrases.paper_specific` for thermodynamic misframing (construct validity = serious) alongside `cliche_patterns` (annoying style preference = not serious).
- Result: researchers either ignore all warnings or spend time fixing em-dash complaints before noticing a broken cross-reference.

The fix: classify by **consequence**. A Critical violation misleads the reader or breaks provenance. A Substantive violation weakens the argument. An Administrative violation is a style preference or annoyance. Each tier gets different build behavior.

---

## Three Tiers

### Critical — Build-blocking

Must be fixed before `seldon paper build` succeeds. These violations produce incorrect or unverifiable output.

- Unresolved `{{result:...}}`, `{{figure:...}}`, or `{{cite:...}}` references
- Glossary banned synonym violations (rejected terms from `check_glossary.py`)
- Missing figure or table captions
- Broken cross-references (`@tbl-name`, `@fig-name` that don't resolve)
- Any claim that is unsupported by registered evidence (unregistered result cited inline)

### Substantive — Flagged loudly, non-blocking

Reported as warnings. Build succeeds. Should be fixed before submission.

These violations weaken the argument, misframe the audience, or reduce claim clarity to the point where a reviewer may question them.

- Sentences over max word count (default 35)
- Hedge stacking: "may potentially", "could possibly", "might perhaps" (weakens claim validity)
- Ambiguous pronouns: "This" or "It" opening a sentence without a clear antecedent
- Nominalizations where the simpler verb form exists ("provides an explanation of" → "explains")
- Audience misframing: bullets in prose, classroom language in research context
- Inconsistent person, tense, or voice (e.g., mixing "we tested" with "the authors tested")
- Rejected framing phrases: project-specific terms that misframe the theoretical claims

### Administrative — Budget-based, non-blocking

Reported as counts vs. budgets. Build succeeds. Tolerable within limits.

These violations are style preferences or annoyances. The author may have a legitimate reason for each individual occurrence; the budget prevents accumulation.

- Em-dashes (default budget: 0 in body text, 3 in tables)
- Self-congratulatory adverbs: "very", "extremely", "highly" (budget per section)
- Cliché patterns (total budget across paper)
- Word repetition within N-paragraph windows (budget per window)
- Banned words with budget 0: "novel", "utilize", "leverage", "robust", etc. (zero tolerance, non-blocking)
- Banned phrases with budget 0: throat-clearing ("it is worth noting"), wordy fillers ("in order to"), etc.

---

## How Tiers Interact with the Build

```
seldon paper build             → all three tiers checked
seldon paper build --strict    → substantive violations also block
seldon paper build --pedantic  → all violations block (final pre-submit polish)
```

Exit codes:
- Critical violations: exit 1
- Substantive or administrative only: exit 0 (with warnings/budget report)
- `--strict` with substantive: exit 1
- `--pedantic` with any violation: exit 1

---

## Report Format

```
CRITICAL (2 violations — BUILD BLOCKED)
  05_results.md:28 — Unresolved reference: {{result:missing_name:value}}
  03_methods.md:15 — Glossary violation: "entropy fitness" (banned: use "log-precision fitness")

SUBSTANTIVE (3 warnings)
  05_results.md:46 — Sentence: 42 words (max 35)
  06_discussion.md:12 — Hedge stack: "may potentially suggest"
  04_experimental_design.md:8 — Ambiguous pronoun: "This demonstrates..."

ADMINISTRATIVE (budgets)
  Em-dashes: 0/0 ✓
  "novel": 0/0 ✓
  "robust": 1/0 ✗ OVER BUDGET (06_discussion.md:33)
  Adverbs (per section): max 1/2 ✓
  Clichés: 2/3 ✓
  Repetition: 1 window over budget (05_results.md ¶3-5: "population" ×4)
```

---

## Per-Project Configuration

All rules are project-level. No global config yet (see Future section). Config file: `paper/paper_qc_config.yaml`.

```yaml
# paper/paper_qc_config.yaml

tiers:
  critical:
    unresolved_references: true        # {{result:...}} that don't resolve
    glossary_violations: true          # Banned synonyms from glossary.md
    missing_captions: true             # Figures/tables without captions
    broken_cross_references: true      # @tbl-name, @fig-name that don't resolve

  substantive:
    max_sentence_words: 35
    hedge_stacking: true               # "may potentially", "could possibly"
    ambiguous_pronouns: true           # "This" or "It" opening a sentence
    nominalizations: true              # Explicit pairs defined below
    tense_consistency: true            # results in past, claims in present
    voice_consistency: true            # first_person: "we"
    no_bullet_points_in_prose: true
    rejected_framing:                  # Project-specific misframing phrases
      - "entropy fitness"
      - "information-theoretic fitness"
      - "thermodynamic interpretation"
      - "hallucination"               # Use "confabulation" per NIST AI 600-1
      - "ablation"                    # Use "knowledge representation study"
      # ... project defines these

  administrative:
    em_dashes:
      budget: 0
      contexts:
        body_text: 0
        tables: 3
    word_budgets:
      - word: "novel"
        budget: 0
      - word: "utilize"
        budget: 0
      - word: "leverage"
        budget: 0
      - word: "robust"
        budget: 0
      - word: "notably"
        budget: 0
      - word: "remarkably"
        budget: 0
      - word: "strikingly"
        budget: 0
      - word: "importantly"
        budget: 0
      - word: "interestingly"
        budget: 0
      - word: "clearly"
        budget: 0
      - word: "obviously"
        budget: 0
      - word: "significant"
        budget: 0
      - word: "impactful"
        budget: 0
      - word: "comprehensive"
        budget: 0
      - word: "groundbreaking"
        budget: 0
      - word: "transformative"
        budget: 0
      - word: "unprecedented"
        budget: 0
      # ... project defines these
    phrase_budgets:
      - phrase: "it is important to note"
        budget: 0
      - phrase: "it is worth noting"
        budget: 0
      - phrase: "it should be noted"
        budget: 0
      - phrase: "it bears mentioning"
        budget: 0
      - phrase: "we would like to point out"
        budget: 0
      - phrase: "in order to"
        budget: 0
      - phrase: "the fact that"
        budget: 0
      - phrase: "for the purpose of"
        budget: 0
      - phrase: "in terms of"
        budget: 0
      - phrase: "with respect to"
        budget: 0
      # ... project defines these
    adverb_frequency:
      words: ["very", "extremely", "highly", "incredibly", "dramatically",
              "tremendously", "vastly", "overwhelmingly", "profoundly"]
      budget_per_section: 2
    cliche_budget: 3                   # Total across paper
    repetition_detection:
      window_paragraphs: 3
      min_word_length: 6
      min_occurrences: 3
      budget_per_window: 3
      exclude:                         # Domain terms that repeat naturally
        - "fitness"
        - "precision"
        - "convergence"
        # ... project defines these
```

---

## Relationship to the Glossary Checker

`check_glossary.py` is the enforcement mechanism for rejected terms. Its violations feed into the Critical tier: any banned synonym from `glossary.md` is a build-blocking error, not a warning.

The config file's `substantive.rejected_framing` list covers phrases that misframe theoretical claims but may not be in the glossary (e.g., full multi-word phrases). The glossary checker handles single rejected terms; `rejected_framing` handles multi-word constructions.

There should be no duplication: a term in the glossary's banned list should not also appear in `rejected_framing`. One enforcement path per violation type.

---

## Migration

The existing leibniz-pi config files (`paper_qc_config.yaml` and `paper_style_config.yaml`) need restructuring into the single unified format above. That is a separate task. This AD defines the target structure; migration is not part of this decision.

During migration:
- All current Tier 2 rules map to Critical or Substantive per the reclassification in Appendix A
- All current Tier 3 rules map to Substantive or Administrative per the reclassification in Appendix A
- The two-file split is eliminated; one `paper_qc_config.yaml` holds everything
- `paper_style_config.yaml` is deprecated after migration

---

## Future: Global Config

A global default config (`~/.seldon/paper_qc_defaults.yaml` or equivalent) is planned but not implemented. When added:

- Global config defines defaults for all projects
- Project-level config overrides global (project takes precedence on conflicts)
- Global config is where "pet peeve" universal bans live (words the author hates in all papers)
- Project-specific framing violations always stay project-level — they have no meaning globally

This AD does not implement global config. All rules are project-level for now.

---

## Appendix A: Reclassification of Existing Leibniz-Pi Rules

### From `paper_qc_config.yaml` (currently "Tier 2 — soft constraints")

| Rule | New Tier | Rationale |
|------|----------|-----------|
| `max_sentence_words: 35` | Substantive | Long sentences weaken comprehension and hide weak reasoning |
| `min_paragraph_sentences: 2` | Administrative | Structural preference; single-sentence paragraphs are sometimes correct |
| `max_paragraph_sentences: 8` | Administrative | Structural preference |
| `no_inline_bold: true` | Administrative | Formatting style; doesn't affect argument validity |
| `no_em_dashes: true` | Administrative (budget 0) | Annoying style preference; zero tolerance, non-blocking |
| `no_bold_pseudo_headers: true` | Administrative | Formatting convention |
| `no_semicolons_over_words: 20` | Substantive | Long semicolon-joined sentences obscure logical structure |
| `max_hedge_per_claim: 1` | Substantive | Hedge stacking weakens argument validity |
| `active_voice_preferred: true` | Substantive | Passive voice obscures agency and reduces claim clarity |
| `first_person: "we"` | Substantive | Inconsistent person framing is audience misframing |
| `tense_results: past` | Substantive | Tense inconsistency creates framing errors |
| `tense_claims: present` | Substantive | Tense inconsistency creates framing errors |
| `lead_with_point: true` | Substantive | Buried topic sentences weaken argumentative structure |
| `one_idea_per_paragraph: true` | Substantive | Multi-idea paragraphs obscure logical flow |
| `flag_ambiguous_pronouns: true` | Substantive | Ambiguous antecedents weaken claim clarity |
| `italic_run_in_heads: true` | Administrative | Formatting convention (APA Level 4 style) |
| `no_bullet_points_in_prose: true` | Substantive | Bullets in prose fragment argument; audience misframing |
| `figures_have_captions: true` | **Critical** | Missing captions violate publication standards |
| `tables_have_captions: true` | **Critical** | Missing captions violate publication standards |

### From `paper_style_config.yaml` (currently "Tier 3 — informational")

| Rule | New Tier | Rationale |
|------|----------|-----------|
| `banned_words.always` (novel, utilize, leverage, robust, notably, etc.) | Administrative (budget 0) | Annoying but don't mislead; zero tolerance budget, non-blocking |
| `banned_words.paper_specific: "hallucination"` | **Substantive** | Misframes the phenomenon per NIST AI 600-1; affects claim precision |
| `banned_words.paper_specific: "ablation"` | **Substantive** | Misframes the study design; construct validity issue |
| `banned_phrases.always` (throat-clearing: "it is worth noting", etc.) | Administrative (budget 0) | Verbal clutter; doesn't mislead; zero budget, non-blocking |
| `banned_phrases.always` (nominalizations: "provides an explanation of", etc.) | Substantive | Weakens prose clarity; reader must do extra processing to recover meaning |
| `banned_phrases.always` (hedge stacking: "may potentially", etc.) | Substantive | Hedge stacking weakens argument validity; same category as `max_hedge_per_claim` |
| `banned_phrases.always` (wordy fillers: "in order to", "the fact that", etc.) | Administrative (budget 0) | Verbose but not misleading |
| `banned_phrases.paper_specific` (thermodynamic framing: "entropy fitness", "free energy", etc.) | **Substantive** | These misframe the mathematical claims — construct validity; wrong theoretical frame |
| `cliche_patterns` | Administrative (budget-based) | Style preference; annoying; doesn't break the argument |
| `repetition_detection` | Administrative (budget-based) | Verbose within windows; acceptable at low levels |
| `self_congratulation.flag_words` (very, extremely, highly, etc.) | Administrative (budget per section) | Hyperbole is annoying but doesn't falsify claims |
| `nominalizations` (explicit verb pairs: "make a decision" → "decide") | Substantive | Nominalizations weaken prose and reader trust; Substantive (could argue Administrative, but the argument effect is real) |
