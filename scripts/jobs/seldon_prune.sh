#!/bin/bash
# seldon-prune: launchd wrapper for `seldon prune run`, the weekly prune (PRUNE-001).
# Task: seldon cc_tasks/2026-10-17_PRUNE-001_weekly_prune_of_open_artifacts.md. Rules and their
# reasons: seldon/core/prune.py; config: seldon.yaml `prune:`. Modelled on seldon_dispatch.sh,
# whose reasons (no inherited environment, Neo4j names only, log caps from seldon.yaml) hold here.
#
# Fires Sunday 03:30 local (scripts/jobs/com.brock.seldon-prune.plist). One run writes one
# `prune_pass` record to this repository's event store whatever it found, and notifies through
# `dispatch.notify` only when it resolved, re-dated or withdrew something, failed a unit, or hit
# the token ceiling. The standing dispatcher's reconciler commits the event-store lines (AD-038-R1).
set -u
export PATH="/opt/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# A test can redirect the log; launchd sets no such variable.
LOG="${SELDON_PRUNE_LOG:-$REPO/logs/seldon_prune.log}"
LOG_DIR="$(dirname "$LOG")"
mkdir -p "$LOG_DIR"

# The sweep makes zero model calls; nothing here may reach a paid API.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# NEO4J CREDENTIALS, exactly as seldon_dispatch.sh reads them: NEO4J_* names only, this repo's
# `.env` first, then ~/.wintermute/.env; never echo a value.
for ENVF in "$REPO/.env" "$HOME/.wintermute/.env"; do
  [ -n "${NEO4J_PASSWORD:-}${NEO4J_PASS:-}" ] && break
  [ -f "$ENVF" ] || continue
  while IFS= read -r line; do
    case "$line" in
      NEO4J_*=*)
        v="${line#*=}"; v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
        export "${line%%=*}"="$v" ;;
    esac
  done < "$ENVF"
  unset v
done
if [ -z "${NEO4J_PASSWORD:-}${NEO4J_PASS:-}" ]; then
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | REFUSING: no Neo4j credentials in the launchd" \
       "environment, $REPO/.env or ~/.wintermute/.env; the prune cannot read the graphs" >> "$LOG"
  exit 3
fi

# Retention, from seldon.yaml `jobs.prune`, never typed here. A missing key refuses.
caps=$(/opt/anaconda3/bin/python3 -c "
import yaml
j = yaml.safe_load(open('$REPO/seldon.yaml'))['jobs']['prune']
print(j['log_max_line_chars'], j['log_max_run_bytes'], j['log_retention_days'])" 2>/dev/null)
if [ -z "$caps" ]; then
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | REFUSING: seldon.yaml jobs.prune log caps" \
       "missing or unreadable" >> "$LOG"
  exit 2
fi
read -r MAX_LINE MAX_RUN RETAIN_DAYS <<< "$caps"

if [ -f "$LOG" ] && [ "$(/usr/bin/stat -f%z "$LOG")" -gt "$MAX_RUN" ]; then
  mv "$LOG" "$LOG.$(date -u +%Y%m%dT%H%M%SZ)"
fi
/usr/bin/find "$LOG_DIR" -name "$(basename "$LOG").*" -mtime "+$RETAIN_DAYS" -delete 2>/dev/null

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | seldon-prune fire"
  cd "$REPO" && /opt/anaconda3/bin/seldon prune run 2>&1 | /usr/bin/cut -c "1-$MAX_LINE"
  rc=${PIPESTATUS[0]}
  echo "=== rc=$rc"
  exit $rc
} >> "$LOG" 2>&1
