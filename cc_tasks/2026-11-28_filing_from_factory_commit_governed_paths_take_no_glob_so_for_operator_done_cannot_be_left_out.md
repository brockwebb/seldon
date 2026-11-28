# Filing from factory: commit-governed paths take only exact files and whole directories, so for_operator/done/ cannot be left out

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-71 (REVIEW-002 finding F-04), a dispatched Claude Code session.

## What was experienced

factory's coordinator tick commits the top-up items it files (`for_operator/<date>_top_up_<project>_<unit>_<week>.md`)
and the grant lines it writes through `seldon commit-governed`. So factory's `desktop_commit.paths` holds the
whole of `for_operator/` (`seldon.yaml`). That also admits `for_operator/done/`, where the operator's answers live and
where the bank reads a top-up's authority. Any session in the primary can then commit a `done/` copy through the
governed path. REVIEW-002 F-04 named it.

## What the evidence shows

`seldon/core/desktop_commit.py` reads `desktop_commit.paths` as directory roots (`dir/`) and exact files. A directory
written without its trailing `/` is refused. There is no glob and no exclusion, so factory cannot declare "the items
in `for_operator/`, not `done/`". The item names are dated, so the tick cannot list them as exact files ahead of time.

## What factory does meanwhile

FAC-71: the tick applies a top-up only from a move it committed itself from the primary's working tree (state
`operator_moved`). A `done/` copy committed through the governed path never appeared as such a move, so it is put to
judgment and no grant is written from it. The commit path itself stays open, which DN-004 ADDENDUM 03 records.

## What factory asks

Could `desktop_commit.paths` accept a glob (for example `for_operator/[0-9]*.md`, with a `*` that does not cross `/`)
or an exclusion (`!for_operator/done/`)? factory would then declare only the items the tick files.
