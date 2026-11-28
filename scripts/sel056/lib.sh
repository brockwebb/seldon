#!/bin/bash
# SEL-063 (REVIEW-001 F-30): what the SEL-056 scripts share, so none of them deletes a directory it did not make or
# names one machine's squiddy. Sourced, never run: `source "$(dirname "$0")/lib.sh"`.

# The marker a scratch directory made here carries; a directory without it is never removed.
SEL056_MARKER=".sel056_scratch"

# The squiddy checkout: $SQUIDDY_ROOT when set, else `../squiddy` beside this repository's PRIMARY checkout (the
# `project_new.squiddy_command` rule: the kit's siblings are the primary's; a worktree under .claude/worktrees has none).
sel056_squiddy_root() {
  if [ -n "${SQUIDDY_ROOT:-}" ]; then
    printf '%s\n' "$SQUIDDY_ROOT"
    return 0
  fi
  local common
  common="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --path-format=absolute --git-common-dir)" || return 1
  (cd "$(dirname "$common")/../squiddy" 2>/dev/null && pwd) || {
    echo "sel056: no squiddy checkout beside $(dirname "$common"); set SQUIDDY_ROOT" >&2
    return 1
  }
}

# Make $1 an empty scratch directory. Refused, writing nothing, unless it resolves under /tmp or $TMPDIR, and is either
# absent or a directory this function made earlier (it holds $SEL056_MARKER).
sel056_fresh_scratch() {
  local want="${1:?sel056_fresh_scratch <dir>}" parent real tmp ok=""
  parent="$(cd "$(dirname "$want")" 2>/dev/null && pwd -P)" || {
    echo "sel056: the parent of $want does not exist" >&2
    return 1
  }
  real="$parent/$(basename "$want")"
  for tmp in /tmp "${TMPDIR:-/tmp}"; do
    tmp="$(cd "$tmp" 2>/dev/null && pwd -P)" || continue
    case "$real/" in
      "$tmp"/?*/) ok=1 ;;
    esac
  done
  if [ -z "$ok" ]; then
    echo "sel056: $real is not under /tmp or \$TMPDIR; refusing to make it a scratch directory" >&2
    return 1
  fi
  if [ -e "$real" ] && [ ! -f "$real/$SEL056_MARKER" ]; then
    echo "sel056: $real exists and was not made by these scripts (no $SEL056_MARKER); refusing to remove it" >&2
    return 1
  fi
  rm -rf "$real" && mkdir -p "$real" && : > "$real/$SEL056_MARKER"
}
