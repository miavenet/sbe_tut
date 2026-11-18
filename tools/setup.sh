#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
JAR="$ROOT/labs/lib/sbe-all-1.42.0.jar"
SHA1=ce5eea47776deb37fd0f0ba9b2a8716c93099b98
SHA256=f60becdb567519a2ed3824ffe285f93adb2159b39ede0b234fc8b1f13736236a
MODE=${1:-setup}
[[ $# -le 1 && ( "$MODE" = setup || "$MODE" = --check || "$MODE" = --jar-only ) ]] || { echo 'usage: tools/setup.sh [--check|--jar-only]' >&2; exit 2; }
next_step() {
  echo 'macOS: install Python 3, a JDK, and Xcode Command Line Tools (xcode-select --install); then run bash tools/setup.sh.' >&2
  echo 'Linux: install Python 3, a JDK, a C++17 compiler, curl, and sha256sum; then run bash tools/setup.sh.' >&2
}
fail() { echo "SETUP PROBLEM: $*" >&2; next_step; exit 2; }
hash_file() {
  if command -v shasum >/dev/null; then shasum -a "$1" "$2" | awk '{print $1}'
  elif command -v "sha${1}sum" >/dev/null; then "sha${1}sum" "$2" | awk '{print $1}'
  else return 1; fi
}
verify_jar() {
  [[ -f "$1" ]] && [[ "$(hash_file 1 "$1")" = "$SHA1" ]] && [[ "$(hash_file 256 "$1")" = "$SHA256" ]]
}
command -v shasum >/dev/null || { command -v sha1sum >/dev/null && command -v sha256sum >/dev/null; } || fail 'need shasum or sha1sum plus sha256sum'
if [[ ! -f "$JAR" && "$MODE" = setup ]]; then
  command -v curl >/dev/null || fail 'curl is missing'
  mkdir -p "$(dirname "$JAR")"
  TMP_JAR=$(mktemp "$ROOT/labs/lib/.download.XXXXXX")
  trap 'rm -f "$TMP_JAR"' EXIT
  curl --fail --location --retry 2 --connect-timeout 10 --max-time 120 \
    'https://repo1.maven.org/maven2/uk/co/real-logic/sbe-all/1.42.0/sbe-all-1.42.0.jar' -o "$TMP_JAR" || fail 'could not download the pinned SBE jar; check network access'
  verify_jar "$TMP_JAR" || fail 'downloaded jar hash mismatch'
  mv "$TMP_JAR" "$JAR"
fi
verify_jar "$JAR" || fail 'pinned SBE jar missing or hash mismatch; run bash tools/setup.sh with network access'
[[ "$MODE" = --jar-only ]] && exit 0
command -v python3 >/dev/null || fail 'python3 is missing'
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || fail 'Python 3.9 or newer is needed by this course'
JAVA_BIN=${JAVA_HOME:+$JAVA_HOME/bin/}java
JAVAC_BIN=${JAVA_HOME:+$JAVA_HOME/bin/}javac
command -v "$JAVA_BIN" >/dev/null || fail 'java is missing'
command -v "$JAVAC_BIN" >/dev/null || fail 'javac is missing'
JAVA_VERSION=$("$JAVA_BIN" -version 2>&1 | head -1) || fail 'java could not run'
JAVAC_VERSION=$("$JAVAC_BIN" -version 2>&1 | head -1) || fail 'javac could not run'
MIN_JAVA=$(python3 - "$JAR" <<'PY'
import struct, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as jar:
    header=jar.read('uk/co/real_logic/sbe/SbeTool.class')[:8]
print(struct.unpack('>H',header[6:8])[0]-44)
PY
) || fail 'could not inspect pinned jar class version'
java_major=$(python3 - "$JAVA_VERSION" <<'PY'
import re,sys
m=re.search(r'version "(\d+)(?:\.(\d+))?',sys.argv[1])
print((int(m[2]) if m[1]=='1' and m[2] else int(m[1])) if m else 0)
PY
)
javac_major=$(python3 - "$JAVAC_VERSION" <<'PY'
import re,sys
m=re.search(r'javac (\d+)(?:\.(\d+))?',sys.argv[1])
print((int(m[2]) if m[1]=='1' and m[2] else int(m[1])) if m else 0)
PY
)
(( java_major >= MIN_JAVA && javac_major >= MIN_JAVA )) || fail "Java/Javac $MIN_JAVA or newer required: SbeTool.class in the pinned jar has class-file major $((MIN_JAVA+44))"
CXX=${CXX:-clang++}
if ! command -v "$CXX" >/dev/null; then
  CXX=g++
  command -v "$CXX" >/dev/null || fail 'no C++ compiler found (clang++ or g++)'
fi
CXX_VERSION=$("$CXX" --version 2>&1 | head -1) || fail 'C++ compiler could not run'
printf 'int main() { return 0; }\n' | "$CXX" -std=c++17 -x c++ -fsyntax-only - >/dev/null 2>&1 || fail 'C++ compiler cannot accept -std=c++17'
if [[ "$JAVA_VERSION" != *'26.0.1'* || "$JAVAC_VERSION" != *'26.0.1'* || "$CXX_VERSION" != *'Apple clang version 21.0.0'* ]]; then
  echo "WARNING: tested with Temurin Java/Javac 26.0.1 and Apple Clang 21.0.0; you have $JAVA_VERSION, $JAVAC_VERSION, $CXX_VERSION; if a lab fails, try the tested versions. Other toolchains and platforms are untested."
fi
printf '%s\n' "$CXX_VERSION" "$JAVA_VERSION" "$JAVAC_VERSION" "jar SHA-1=$SHA1" "jar SHA-256=$SHA256" 'SETUP PASS'
