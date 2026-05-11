#!/usr/bin/env bash
# Verify command for the Study-Now decoupling autoresearch loop.
# Outputs a single integer: passed_scenarios * 10 + checklist_score.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && cd .. && pwd)"
PY="${ROOT}/out/pyenv/bin/python"
[ -x "$PY" ] || PY="python3"

PASS=0
TOTAL=0
LOG="$HERE/.last_run.log"
"$PY" "$HERE/test_decoupling.py" >"$LOG" 2>&1
while IFS= read -r line; do
    # Only count the "fixed" implementation rows — those are the ones that
    # exercise the production code path under test.
    case "$line" in
        \[fixed\]*pass=True*) PASS=$((PASS+1)); TOTAL=$((TOTAL+1));;
        \[fixed\]*pass=False*) TOTAL=$((TOTAL+1));;
    esac
done <"$LOG"

CHECK=$("$PY" "$HERE/checklist.py" 2>/dev/null)
[ -z "$CHECK" ] && CHECK=0
SCORE=$((PASS * 10 + CHECK))
echo "$SCORE"
