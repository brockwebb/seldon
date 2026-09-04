#!/bin/sh
# Reproducible evidence that the test suite is safe to run concurrently.
#
# Background: every Neo4j-backed test wipes its database with
# `MATCH (n) DETACH DELETE n` before it runs (tests/conftest.py::clean_test_db).
# Until 2026-09-04 every test shared one database named `seldon-test`, so two
# pytest processes destroyed each other's fixtures mid-test (defect sweep
# 2026-09-03, RESULT §9.1). tests/testdb.py now gives every pytest process its
# own database.
#
# Usage (from the repo root):
#   sh scripts/test_db_concurrency_check.sh control   # 2 procs, ONE shared DB
#   sh scripts/test_db_concurrency_check.sh fixed     # 2 procs, per-process DBs
#   sh scripts/test_db_concurrency_check.sh fixed4    # 4 procs, per-process DBs
#   sh scripts/test_db_concurrency_check.sh full      # 2 procs, the FULL suite
#
# `control` forces both processes onto one database via SELDON_TEST_DATABASE and
# is expected to FAIL — it is the negative control that shows the defect is real.
# Every other mode is expected to pass.
#
# Logs are written to ./_conc/ (gitignored scratch; delete when done).
set -u

MODE="${1:-fixed}"
SUBSET="tests/test_sync.py tests/test_task_lifecycle.py tests/test_verify.py"
LOGDIR="_conc"
mkdir -p "$LOGDIR"
rm -f "$LOGDIR"/*.log

run_one() {
    python -m dotenv -f .env run -- python -m pytest $TARGET -q > "$LOGDIR/$MODE-$1.log" 2>&1
    echo "process $1 exit=$?"
}

TARGET="$SUBSET"
case "$MODE" in
    control)
        SELDON_TEST_DATABASE=seldon-test
        export SELDON_TEST_DATABASE
        run_one A & run_one B & wait
        ;;
    fixed)
        unset SELDON_TEST_DATABASE 2>/dev/null || true
        run_one A & run_one B & wait
        ;;
    fixed4)
        unset SELDON_TEST_DATABASE 2>/dev/null || true
        run_one A & run_one B & run_one C & run_one D & wait
        ;;
    full)
        unset SELDON_TEST_DATABASE 2>/dev/null || true
        TARGET="tests/"
        run_one A & run_one B & wait
        ;;
    *)
        echo "unknown mode: $MODE (expected control|fixed|fixed4|full)" >&2
        exit 2
        ;;
esac

echo "----- summaries -----"
for f in "$LOGDIR"/*.log; do
    echo "$f: $(tail -n 1 "$f")"
done
