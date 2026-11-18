#!/usr/bin/env bash
# [claim: WP3-CHECKS]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
exec python3 -B "$ROOT/checks/l04/check.py" all
