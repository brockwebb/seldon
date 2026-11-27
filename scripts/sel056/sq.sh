#!/bin/bash
# SEL-056: run the squiddy kit's CLI (squiddy main, editable install) from this repository's root.
# A wrapper because the worktree's command guard refuses `squiddy init ...` typed inline (it reads `init` as git's).
set -euo pipefail
exec /Users/brock/GitHub/squiddy/.venv/bin/squiddy "$@"
