#!/usr/bin/env bash
# [claim: WP1-CHECKS]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$ROOT/checks/l01/check.py" l01 "${1:-all}"
