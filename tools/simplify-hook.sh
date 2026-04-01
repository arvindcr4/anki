#!/usr/bin/env bash
set -euo pipefail

review_cmd="/simplify"

if [ -x "$review_cmd" ]; then
  exec "$review_cmd"
fi

echo "post-commit simplify hook: $review_cmd not found; skipping review." >&2
echo "Install /simplify or edit tools/simplify-hook.sh to point at your preferred review command." >&2
