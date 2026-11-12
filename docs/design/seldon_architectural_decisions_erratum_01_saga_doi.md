# seldon_architectural_decisions erratum 01: the Saga citation's DOI names a different paper

**Date:** 2026-11-11. **Corrects:** `docs/design/seldon_architectural_decisions.md`, the reference list (line 385) and
the PL-011 / evaluation-table citations of Saga (lines 313 and 413). The base note is not edited (immutable once
committed). **Found by:** SEL-036's resolution of every governed citation (`graphs/seldon-biblio`, resolver
`sel036-resolve/2`); **verified for this erratum:** SEL-037 Part D, against Crossref on 2026-11-12 (UTC) and against the
note's own text.

## What was wrong

| the note says | the work it is | its identifier | seldon-biblio entry |
|---|---|---|---|
| "Ilyas, I. F., et al. (2022). Saga: A platform for continuous construction and serving of knowledge at scale. *Proceedings of the ACM on Management of Data (SIGMOD 2022)*. https://doi.org/10.1145/3514221.3526052" (line 385) | Ilyas, Rekatsinas, Konda, Pound, Qi and Soliman, "Saga: A Platform for Continuous Construction and Serving of Knowledge at Scale", Proceedings of the 2022 International Conference on Management of Data (SIGMOD 2022) | doi:10.1145/3514221.3526049 | `ilyas2022saga` |

The DOI the note gives, `10.1145/3514221.3526052`, is a real DOI in the same proceedings for a different paper:
Crossref answers it as "Deploying a Steered Query Optimizer in Production at Microsoft" (authors including Zhang,
Interlandi, Mineiro, Qiao, Ghazanfari, Lie, Friedman, Hosn, Patel and Jindal). `10.1145/3514221.3526049` is Saga's, by
Crossref's record and by arXiv's record of 2204.07309.

## Preprint and published version

The note also cites Saga as "Ilyas et al. arXiv:2204.07309" (line 413). That is the preprint of the same work; the
published version is now the record. Both identifiers name it: arXiv:2204.07309 (preprint) and
doi:10.1145/3514221.3526049 (SIGMOD 2022). The seldon-biblio entry `ilyas2022saga` holds both.

## Effect on the note

None on its reasoning: PL-011 rests on what Saga describes, and the work is the one the note names by title and
authors. Only the link was wrong. A reader following the DOI reached the Microsoft paper.
