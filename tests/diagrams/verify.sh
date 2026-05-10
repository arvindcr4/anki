#!/bin/bash
# Hybrid metric: (passed pytest tests) * 10 + checklist points.
# Outputs a single integer on stdout. Suitable as the autoresearch Verify command.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/out/pyenv/bin/python"

# 1) Pytest count
TEST_OUT=$("$PY" -m pytest "$ROOT/tests/diagrams/test_diagrams.py" -q --no-header 2>&1 || true)
PASSED=$(echo "$TEST_OUT" | grep -oE "[0-9]+ passed" | head -1 | grep -oE "^[0-9]+")
PASSED=${PASSED:-0}

# 2) Checklist
CHECKLIST=$("$PY" "$ROOT/tests/diagrams/checklist.py" 2>/dev/null || echo 0)
CHECKLIST=${CHECKLIST:-0}

echo $((PASSED * 10 + CHECKLIST))
