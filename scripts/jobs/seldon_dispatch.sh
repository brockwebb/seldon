#!/bin/bash
# seldon-dispatch: launchd wrapper for `seldon dispatch once` in /Users/brock/GitHub/seldon.
# Task: seldon cc_tasks/2026-10-09_SEL-005_standing_dispatcher_for_seldon_and_squiddy.md.
# Design: seldon docs/design/2026-09-15_standing_dispatcher.md ("Adopting it in another project");
# modelled on ai-readiness-kg scripts/jobs/airkg_dispatch.sh, whose reasons are kept here.
#
# Fires every poll_interval_s. A pass exits 0 on every ordinary outcome (disabled, STOP file,
# lease held, nothing eligible), so launchd never learns to treat a healthy pass as a failure.
set -u
# The anaconda python carries seldon and neo4j. A dispatched session launches the CLI named in
# seldon's model lock by absolute path (AD-035 R3), so PATH no longer chooses the binary.
export PATH="/opt/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
# SEL-010R2 (AD-038-R11): `seldon dispatch adopt` writes another project's plist to run THIS wrapper with that
# project's root and its plist as the two arguments. With none, the project is this checkout, as before.
REPO="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"
# A test can redirect the log; launchd sets no such variable.
LOG="${SELDON_DISPATCH_LOG:-$REPO/logs/seldon_dispatch.log}"
LOG_DIR="$(dirname "$LOG")"
mkdir -p "$LOG_DIR"
# A test can run the wrapper without a pass (SEL-025's rotation fixture); launchd sets no such variable.
SELDON_BIN="${SELDON_DISPATCH_BIN:-/opt/anaconda3/bin/seldon}"

# DD-007: subscription OAuth only; the dispatcher refuses a pass when either is set.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# NEO4J CREDENTIALS. A launchd job inherits almost no environment (ai-readiness-kg's first
# scheduled pass died on AuthError for this). Read NEO4J_* names only, from this repo's own
# `.env` first (R-11: credentials live there), then ~/.wintermute/.env; never echo a value. One
# surrounding quote pair is stripped, as `.strip('"').strip("'")` would.
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
       "environment, $REPO/.env or ~/.wintermute/.env; a pass cannot read the queue" >> "$LOG"
  exit 3
fi

# seldon.yaml poll_interval_s and the plist's StartInterval are one parameter written twice;
# refuse rather than let them drift.
PLIST="${2:-$REPO/scripts/jobs/com.brock.seldon-dispatch.plist}"
declared=$(/opt/anaconda3/bin/python3 -c "
import yaml
print(yaml.safe_load(open('$REPO/seldon.yaml'))['dispatch']['poll_interval_s'])" 2>/dev/null)
in_plist=$(/usr/bin/awk '/<key>StartInterval<\/key>/{getline; gsub(/[^0-9]/,""); print; exit}' \
  "$PLIST" 2>/dev/null)
if [ -z "$declared" ] || [ -z "$in_plist" ] || [ "$declared" != "$in_plist" ]; then
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | REFUSING: poll_interval_s=$declared but the" \
       "plist StartInterval=$in_plist; change both or neither" >> "$LOG"
  exit 2
fi

# Retention, from seldon.yaml `jobs.dispatch`, never typed here. A missing key refuses.
caps=$(/opt/anaconda3/bin/python3 -c "
import yaml
j = yaml.safe_load(open('$REPO/seldon.yaml'))['jobs']['dispatch']
print(j['log_max_line_chars'], j['log_max_run_bytes'], j['log_retention_days'])" 2>/dev/null)
if [ -z "$caps" ]; then
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | REFUSING: seldon.yaml jobs.dispatch log caps" \
       "missing or unreadable" >> "$LOG"
  exit 2
fi
read -r MAX_LINE MAX_RUN RETAIN_DAYS <<< "$caps"

# Rotate before the run, so a pass can never be truncated mid-write.
# SEL-025 (AD-038-R22): the rotated name keeps `.log` LAST and lives under `logs/dispatch/`. The old name,
# `<log>.<stamp>`, matched no ignore rule (`*.log` needs the suffix last), so each rotation left an untracked file
# that refused the whole queue on c7: three days, 2026-11-04 02:19Z to 2026-11-06 12:55Z. `.gitignore` also ignores
# `logs/**`, so either half alone keeps the tree clean.
ROT_DIR="$LOG_DIR/dispatch"
ROT_BASE="$(basename "$LOG" .log)"
if [ -f "$LOG" ] && [ "$(/usr/bin/stat -f%z "$LOG")" -gt "$MAX_RUN" ]; then
  mkdir -p "$ROT_DIR"
  mv "$LOG" "$ROT_DIR/$ROT_BASE.$(date -u +%Y%m%dT%H%M%SZ).log"
fi
# Retention matches the rotation's own name only: `logs/dispatch/` also holds each dispatched session's log, which
# this job does not own. The second `find` expires rotations made under the old name before SEL-025.
/usr/bin/find "$ROT_DIR" -maxdepth 1 -name "$ROT_BASE.*.log" -mtime "+$RETAIN_DAYS" -delete 2>/dev/null
/usr/bin/find "$LOG_DIR" -maxdepth 1 -name "$(basename "$LOG").*" -mtime "+$RETAIN_DAYS" -delete 2>/dev/null

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) | seldon-dispatch fire"
  cd "$REPO" && "$SELDON_BIN" dispatch once 2>&1 | /usr/bin/cut -c "1-$MAX_LINE"
  rc=${PIPESTATUS[0]}
  echo "=== rc=$rc"
  exit $rc
} >> "$LOG" 2>&1
