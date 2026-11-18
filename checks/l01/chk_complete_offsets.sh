#!/usr/bin/env bash
# [claim: WP1-NUMERIC]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
exec python3 "$ROOT/checks/l01/numeric.py" completion
