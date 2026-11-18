#!/usr/bin/env bash
# [claim: WP2-CHECKS]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
exec python3 -B "$ROOT/checks/l03/schema.py"
