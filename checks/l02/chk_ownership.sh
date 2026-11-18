#!/usr/bin/env bash
# [claim: WP1-CHECKS]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
exec "$ROOT/checks/chk_l02_buffers.sh" ownership
