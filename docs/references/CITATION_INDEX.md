# Global Citation Catalog — Index

**File:** `references.bib`
**Per:** AD-017 (Central Validity Ontology)
**Purpose:** Single canonical bibliography for all Seldon-tracked projects.

## Usage

- Vocabulary files cite using BibTeX keys from this catalog (e.g., `[ShadishCookCampbell2002]`)
- Project-specific `.bib` files may continue to exist for their own papers
- If a source is shared across projects, it should be here
- **Blast radius:** To find what depends on a source, grep the citation key across all repos

## Quick Reference

### Framework Documents (NIST, FCSM, OMB)

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `fcsm2020` | FCSM 20-04 Data Quality Framework | crosswalk paper, census-mcp paper, validity vocabulary |
| `fcsm2025` | FCSM 25-03 AI-Ready Federal Statistical Data | ai4stats |
| `ncses2025` | NCSES RFS MLMU-25: Measuring LLM Understanding of Federal Statistical Data | census-mcp paper |
| `nist2023airm` | NIST AI RMF 1.0 | crosswalk paper, census-mcp paper, validity vocabulary |
| `nist2023crosswalks` | NIST AI RMF Crosswalks resource page | crosswalk paper |
| `nist2023playbook` | NIST AI RMF Playbook | crosswalk paper |
| `nist2024genai` | NIST AI 600-1 Generative AI Profile | crosswalk paper, validity vocabulary, SFV paper |
| `omb2025m2521` | OMB M-25-21: Accelerating Federal Use of AI | SFV paper |

### Statutes and Regulations

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `eo13642` | EO 13642: Open and Machine Readable Default | census-mcp paper |
| `iqa2000` | Information Quality Act (P.L. 106-554) | crosswalk paper |
| `naiia2020` | National AI Initiative Act of 2020 | crosswalk paper |
| `obama2009ogd` | Open Government Directive (OMB M-10-06) | census-mcp paper |
| `omb_directive4` | OMB Statistical Policy Directive No. 4 | crosswalk paper |
| `open_gov_data2018` | OPEN Government Data Act | crosswalk paper |

### Foundational Methodology

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `CronbachMeehl1955` | Construct validity / reliability distinction | validity vocabulary |
| `Groves2009` | Survey Methodology (Total Survey Error) | validity vocabulary, ai4stats |
| `Hirstein2005` | Brain Fiction (confabulation — clinical origin) | validity vocabulary, crosswalk paper |
| `kahneman2021` | Noise: A Flaw in Human Judgment | census-mcp paper |
| `morris1938` | Foundations of the Theory of Signs | census-mcp paper |
| `cohen1960coefficient` | Cohen's kappa (inter-rater agreement) | SFV paper |
| `landis1977measurement` | Landis & Koch agreement benchmarks | SFV paper |
| `ShadishCookCampbell2002` | Experimental and Quasi-Experimental Designs (classical validity types) | validity vocabulary, SFV paper |

### AI/ML Methodology and Governance

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `edge2024graphrag` | GraphRAG (Microsoft) | census-mcp paper |
| `lewis2020rag` | Retrieval-Augmented Generation (NeurIPS 2020) | census-mcp paper |
| `bryan2025agentic` | MS AI Red Team: Agentic AI failure taxonomy | SFV paper |
| `chen2026sweci` | SWE-CI: AI coding agent codebase maintenance | SFV paper, ai-workflow-design |
| `gebru2021datasheets` | Datasheets for Datasets | SFV paper |
| `mitchell2019model` | Model Cards for Model Reporting | SFV paper |
| `openai2025agents` | OpenAI: A Practical Guide to Building Agents | SFV paper |
| `schluntz2024agents` | Anthropic: Building Effective Agents | SFV paper |
| `wiesinger2024agents` | Google: Agents whitepaper | SFV paper |
| `zheng2023judging` | LLM-as-a-Judge / MT-Bench | census-mcp paper |

### Webb (Own Published Work)

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `Webb2025censusmcp` | open-census-mcp-server (GitHub software) | census-mcp paper |
| `Webb2026ai4stats` | AI for Official Statistics (SFV chapter) | validity vocabulary |
| `Webb2026crosswalk` | FCSM/NIST crosswalk (Zenodo preprint) | crosswalk paper, census-mcp paper, validity vocabulary, SFV paper |
| `Webb2026pragmatics` | Pragmatics: Deterministic Context Engineering (Zenodo) | SFV paper |

## Key Normalization Note

Personal-author keys use `AuthorYearKeyword` (capital first letter): `Webb2026crosswalk`, `ShadishCookCampbell2002`.
Institutional-author keys use lowercase abbreviation: `fcsm2020`, `nist2023airm`.

Project-level `.bib` files (e.g., crosswalk paper, census-mcp) may use the older lowercase variant
`webb2026crosswalk`. The canonical key in this catalog is `Webb2026crosswalk`. Both resolve to the same
source; note discrepancy if doing cross-repo blast radius analysis.

## Maintenance

When adding a new source:
1. Add the BibTeX entry to `references.bib` in the correct section, alphabetically by key
2. Add a row to the Quick Reference table above with the key and which projects use it
3. If replacing/updating an existing source, grep the old key across all repos to assess blast radius
