#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
"$ROOT/tools/setup.sh" --jar-only
for key in JAVA_TOOL_OPTIONS JDK_JAVA_OPTIONS _JAVA_OPTIONS; do
  [[ -z "${!key:-}" ]] || { echo "INFRA: unset $key for reproducible JVM options" >&2; exit 2; }
done
JAVA_BIN=${JAVA_HOME:+$JAVA_HOME/bin/}java
JAR="$ROOT/labs/lib/sbe-all-1.42.0.jar"
JVM=(--add-opens java.base/jdk.internal.misc=ALL-UNNAMED)
if [[ ${1:-} = --run ]]; then
  [[ $# -ge 3 ]] || { echo 'usage: sbe_tool.sh --run CLASSPATH MAIN [args...]' >&2; exit 2; }
  CP=$2; shift 2
  exec "$JAVA_BIN" "${JVM[@]}" -cp "$CP:$JAR" "$@"
fi
PROPS=(); INPUTS=(); OUTPUT=''
for arg in "$@"; do
  case "$arg" in
    -Dsbe.output.dir=*) [[ -z "$OUTPUT" ]] || exit 2; OUTPUT=${arg#*=} ;;
    -Dsbe.generate.access.order.checks=*) echo 'INFRA: stale property; use sbe.generate.precedence.checks plus the C++ compile macro' >&2; exit 2 ;;
    -Dsbe.validation.xsd=*|-Dsbe.xinclude.aware=*|-Dsbe.validation.stop.on.error=*) echo 'INFRA: strict XSD gate cannot be overridden' >&2; exit 2 ;;
    -D*) PROPS+=("$arg") ;;
    -*) echo "INFRA: unexpected option $arg" >&2; exit 2 ;;
    *) INPUTS+=("$arg") ;;
  esac
done
[[ -n "$OUTPUT" && ${#INPUTS[@]} -gt 0 ]] || { echo 'usage: sbe_tool.sh -Dsbe.output.dir=NEW_DIR [-Dproperty=value ...] schema.xml|schema.sbeir ...' >&2; exit 2; }
[[ ! -e "$OUTPUT" ]] || { echo 'INFRA: output must be a new directory (publish complete generations only)' >&2; exit 2; }
mkdir -p "$(dirname "$OUTPUT")"
STAGE=$(mktemp -d "$(dirname "$OUTPUT")/.sbe-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
"$JAVA_BIN" "${JVM[@]}" -cp "$JAR" "$ROOT/labs/common/StrictSbe.java" "${INPUTS[@]}"
"$JAVA_BIN" "${JVM[@]}" "${PROPS[@]}" "-Dsbe.output.dir=$STAGE" -jar "$JAR" "${INPUTS[@]}"
mv "$STAGE" "$OUTPUT"
