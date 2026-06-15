#!/usr/bin/env bash
# PreToolUse(Edit|Write) guard — reminder only, non-blocking.
#
# The cluster-validation engine work must land in NEW files for clean upstream
# PRs (see cluster-validation-plugin design spec). When Claude is about to edit
# a file that upstream ROCm/cvs already tracks, inject a reminder to keep the
# diff minimal. New files (ours) pass through silently.

input=$(cat)
fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

[ -n "$fp" ] || exit 0

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Only guard files inside this repo.
case "$fp" in
  "$repo_root"/*) ;;
  *) exit 0 ;;
esac

# Never guard .claude/ itself or docs.
case "$fp" in
  "$repo_root"/.claude/*) exit 0 ;;
esac

# Only warn for files tracked in git (upstream files). Our new modules are
# untracked until we commit them, and even then the reminder costs little.
if git -C "$repo_root" ls-files --error-unmatch "${fp#"$repo_root"/}" >/dev/null 2>&1; then
  cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "REMINDER: This file is tracked by upstream ROCm/cvs. The engine-layer rule is: new functionality goes in NEW files (cvs/lib/compare_lib.py, cvs/lib/preflight_lib.py, cvs/cli_plugins/{preflight,baseline,compare}_plugin.py + their unittests). If you must touch this upstream file (e.g., plugin registration), keep the diff to the minimum lines required so the upstream PR stays reviewable."
  }
}
JSON
fi
exit 0
