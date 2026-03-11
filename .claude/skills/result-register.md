---
name: result-register
description: Register a quantitative result with full provenance. Use whenever a computation produces a number, comparison, or measurement that may be cited or built upon later.
---

# Result Registration

When a computation produces a result that matters — a trace comparison, a statistical output, a validation metric, a count — register it immediately. Do not defer. Unregistered results drift, get misquoted, and lose provenance.

## When to Use

- A trace comparison produces a match/mismatch count
- A statistical computation produces a number that will be cited
- A validation step passes or fails
- A benchmark produces performance metrics
- Any time you think "I should remember this number"

## Procedure

1. **Create a result file** in `output/results/` (create the directory if it doesn't exist):

   Filename: `YYYY-MM-DD_<descriptive-slug>.yaml`

```yaml
# Result Registration
id: result-YYYYMMDD-HHMMSS-<short_slug>
date: YYYY-MM-DDTHH:MM:SSZ
description: >
  [One-line plain English description of what this result represents]

value:
  primary: [the number or outcome]
  units: [units, or "dimensionless", or "boolean", or "count"]
  precision: [number of significant digits, or "exact"]

status: provisional  # provisional | verified | published | stale

provenance:
  generated_by: [absolute path to script or command]
  command: [exact command that produced this result]
  input_data:
    - path: [absolute path to input file]
      hash: [sha256 hash, or "not captured"]
    # additional inputs as needed
  input_parameters:
    # key-value pairs of any parameters that affect the result
  environment:
    python_version: [if relevant]
    key_packages: [if relevant]

verification:
  method: [how this was or should be verified]
  verified_by: [null if not yet verified, or "automated_test" or "manual_review"]
  verified_date: [null or date]
  test_file: [absolute path to test that verifies this, if exists]

dependencies:
  requires: []     # IDs of other results this depends on
  blocks: []       # IDs of results or artifacts that depend on this
  related_to: []   # IDs of related results for context

notes: >
  [Any caveats, edge cases, or context needed to interpret this result correctly]
```

2. **Link to the handoff** — mention the result ID in the session closeout handoff

3. **If the result supersedes a previous result**, update the old result's status to `stale` and add a `superseded_by` field pointing to the new result ID

## Verification

A result moves from `provisional` to `verified` when:
- An automated test confirms it is reproducible, OR
- The generating script is re-run and produces the same value, OR
- A trace comparison matches within tolerance

A result moves to `stale` when:
- Its input data changes
- Its generating script changes
- A dependency changes
- A re-run produces a different value

## Context Efficiency

- The YAML file IS the registration. No database needed yet.
- These files are grep-able, diff-able, and readable by both humans and future Seldon CLI.
- When Seldon's engine exists, these YAML files become the migration source.
