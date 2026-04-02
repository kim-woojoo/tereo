#!/usr/bin/env bash
set -euo pipefail

if python3 -m tereo --help >/dev/null 2>&1; then
  TEREO=(python3 -m tereo)
elif command -v tereo >/dev/null 2>&1 && tereo --help >/dev/null 2>&1; then
  TEREO=(tereo)
else
  echo "Install tereo first: pip install tereo" >&2
  exit 1
fi

exec "${TEREO[@]}" demo
