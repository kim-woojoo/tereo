#!/usr/bin/env bash
set -euo pipefail

marker="<!-- tereo:receipt -->"
repo="${GITHUB_REPOSITORY:-${REPO:-}}"
pr_number="${1:-${PR_NUMBER:-}}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to post the TEREO PR comment." >&2
  exit 1
fi

if [[ -z "${pr_number}" && -n "${GITHUB_EVENT_PATH:-}" && -f "${GITHUB_EVENT_PATH}" ]]; then
  pr_number="$(
    python3 - "$GITHUB_EVENT_PATH" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

pull_request = payload.get("pull_request") or {}
print(pull_request.get("number") or "")
PY
  )"
fi

if [[ -z "${repo}" ]]; then
  echo "Set GITHUB_REPOSITORY or REPO before running the PR comment script." >&2
  exit 1
fi

if [[ -z "${pr_number}" ]]; then
  echo "Set PR_NUMBER or pass the pull request number as the first argument." >&2
  exit 1
fi

body="$(cat)"
if [[ -z "${body//[[:space:]]/}" ]]; then
  echo "The PR comment body was empty." >&2
  exit 1
fi

final_body="${body}"$'\n\n'"${marker}"

comment_id="$(
  gh api "repos/${repo}/issues/${pr_number}/comments?per_page=100" \
    | TEREO_MARKER="$marker" python3 -c 'import json, os, sys
comments = json.load(sys.stdin)
marker = os.environ["TEREO_MARKER"]
matches = [str(comment["id"]) for comment in comments if marker in (comment.get("body") or "")]
print(matches[-1] if matches else "")
'
)"

if [[ -n "${comment_id}" ]]; then
  gh api \
    --method PATCH \
    "repos/${repo}/issues/comments/${comment_id}" \
    -f body="$final_body" >/dev/null
  echo "Updated TEREO PR comment ${comment_id} on PR #${pr_number}."
else
  gh api \
    --method POST \
    "repos/${repo}/issues/${pr_number}/comments" \
    -f body="$final_body" >/dev/null
  echo "Created TEREO PR comment on PR #${pr_number}."
fi
