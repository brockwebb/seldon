# cc5_sleep_function_architecture erratum 01: four of its prior-art works are attributed to the wrong authors

**Date:** 2026-11-11. **Corrects:** `docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md`, its
numbered prior-art list (items 1, 2, 5 and 6). The base note is not edited (immutable once committed). **Found by:**
SEL-036's resolution of every governed citation (`graphs/seldon-biblio`, resolver `sel036-resolve/2`: a title match
is confirmed only when a cited author's surname or the cited identifier agrees). **Verified for this erratum:**
SEL-037 Part D, against Crossref (item 1) and the catalog's confirming authority (items 2, 5 and 6) on 2026-11-12
(UTC), and against the note's own text.

## What was wrong

Each title and identifier the note gives is right. The authors are not, and so neither is the "et al." name a reader
would search by. Item 1's year and venue are wrong as well.

| item | the note says | the work it is | its identifier | seldon-biblio entry |
|---|---|---|---|---|
| 1 | "Adler et al. (2021). "Incremental Multi-source Entity Resolution for Knowledge Graph Completion." VLDB-adjacent proceedings." | Saeedi, Peukert and Rahm (2020), "Incremental Multi-source Entity Resolution for Knowledge Graph Completion", *The Semantic Web: ESWC 2020*, Lecture Notes in Computer Science (Springer) | doi:10.1007/978-3-030-49461-2_23 | `adler2021incremental` |
| 2 | "Li et al. (2024). "Knowledge Graph Large Language Model (KG-LLM) for Link Prediction." arXiv:2403.07311." | Shu, Chen, Jin, Zhang, Zhang, Du and Zhang (2024), "Knowledge Graph Large Language Model (KG-LLM) for Link Prediction", Asian Conference on Machine Learning (ACML 2024) | arXiv:2403.07311 (doi:10.48550/arXiv.2403.07311) | `li2024kgllm` |
| 5 | "Xiang et al. (2025). "SplitE: Enhancing Knowledge Graph Embedding Precision with Entity Split and Contextualization." ACM Trans. Recommender Systems." | Wang, Wang, Huang, Zeng, Wang, Srinivasan, Chen, Wu, Yao and Li (2025), "SplitE: Enhancing Knowledge Graph Embedding Precision with Entity Split and Contextualization", ACM Transactions on Recommender Systems | doi:10.1145/3768620 | `xiang2025splite` |
| 6 | "Ebraheem et al. (2016/2021). "Deep Indexed Active Learning for Matching Heterogeneous Entity Representations." arXiv:2104.03986." | Jain, Sarawagi and Sen (2021), "Deep Indexed Active Learning for Matching Heterogeneous Entity Representations", Proceedings of the VLDB Endowment 15(1) | doi:10.14778/3485450.3485455; preprint arXiv:2104.03986 | `arxiv_2104_03986` |

The entry ids keep the name the note cited (`adler2021incremental`, `li2024kgllm`, `xiang2025splite`): an id is the
key the governed Citation already resolves to (AD-036 ADDENDUM 12, R22), and it is never renamed. Each entry's
`authors` are the record's, and its `citation_discrepancies` say what the note got wrong.

## Preprint and published version

Item 6 cites the preprint arXiv:2104.03986; the record is its published version, PVLDB 2021
(doi:10.14778/3485450.3485455). Both identifiers name the one work, and `arxiv_2104_03986` holds both. Item 2's record
is the arXiv preprint with an ACML 2024 venue; seldon-biblio holds no DOI for a proceedings version.

## Effect on the note

None on its design: each work is applied for what its title and abstract describe, and those are the works cited.
A reader searching "Adler et al. 2021", "Li et al. KG-LLM", "Xiang et al. SplitE" or "Ebraheem et al." would find the
wrong paper or none.
