#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Uso: ./tools/run_smoke_tests.sh 'ADMIN_PASSWORD' [admin_user] [--deep-nl]" >&2
  exit 2
fi

ADMIN_PASSWORD="$1"
ADMIN_USER="${2:-admin}"
DEEP_FLAG="${3:-}"

cd "$(dirname "$0")/.."

if [[ "$DEEP_FLAG" == "--deep-nl" ]]; then
  python tools/smoke_test_tesis.py --admin-user "$ADMIN_USER" --admin-pass "$ADMIN_PASSWORD" --deep-nl
else
  python tools/smoke_test_tesis.py --admin-user "$ADMIN_USER" --admin-pass "$ADMIN_PASSWORD"
fi
