#!/bin/bash
# SEL-056: run the squiddy kit's CLI (squiddy main, editable install) from this repository's root.
# A wrapper because the worktree's command guard refuses `squiddy init ...` typed inline (it reads `init` as git's).
# SEL-063 (REVIEW-001 F-30): the kit beside the primary checkout, or $SQUIDDY_ROOT (lib.sh), not one machine's path.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
root="$(sel056_squiddy_root)"
exec "$root/.venv/bin/squiddy" "$@"
