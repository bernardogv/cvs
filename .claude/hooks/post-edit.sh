#!/usr/bin/env bash
# PostToolUse(Edit|Write) for *.py in this repo:
#   1. ruff format + ruff check --fix with the repo-pinned ruff (.ruff_venv)
#   2. run the module's matching unittest file if one exists (TDD feedback)
#   3. warn when a file crosses the 500-line limit
# Exit 2 (stderr -> Claude) only when there is something Claude must act on.

input=$(cat)
fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

[ -n "$fp" ] || exit 0
case "$fp" in *.py) ;; *) exit 0 ;; esac
[ -f "$fp" ] || exit 0

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
case "$fp" in "$repo_root"/*) ;; *) exit 0 ;; esac

msgs=""

# --- 1. ruff (repo-pinned if available, else PATH) -------------------------
ruff="$repo_root/.ruff_venv/bin/ruff"
[ -x "$ruff" ] || ruff="$(command -v ruff || true)"
if [ -n "$ruff" ]; then
  "$ruff" format "$fp" >/dev/null 2>&1 || true
  lint_out=$("$ruff" check --fix --quiet "$fp" 2>&1) || \
    msgs="${msgs}ruff check (after --fix) still reports:\n${lint_out}\n"
fi

# --- 2. related unittests ---------------------------------------------------
base="$(basename "$fp" .py)"
test_file=""
case "$fp" in
  */unittests/*) ;;  # editing a test file itself: skip auto-run, Claude runs tests explicitly in TDD
  */cvs/lib/*)         t="$repo_root/cvs/lib/unittests/test_${base}.py";         [ -f "$t" ] && test_file="$t" ;;
  */cvs/cli_plugins/*) t="$repo_root/cvs/cli_plugins/unittests/test_${base}.py"; [ -f "$t" ] && test_file="$t" ;;
esac
if [ -n "$test_file" ]; then
  test_out=$(cd "$repo_root" && python -m pytest "$test_file" -q -x --no-header 2>&1 | tail -15) || \
    msgs="${msgs}Related tests FAILED (${test_file#"$repo_root"/}):\n${test_out}\n"
fi

# --- 3. 500-line limit -------------------------------------------------------
lines=$(wc -l < "$fp" | tr -d ' ')
if [ "$lines" -gt 500 ]; then
  msgs="${msgs}FILE LENGTH: ${fp#"$repo_root"/} is ${lines} lines (limit 500). Split it before continuing.\n"
fi

if [ -n "$msgs" ]; then
  printf '%b' "$msgs" >&2
  exit 2
fi
exit 0
