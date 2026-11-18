#!/usr/bin/env bash
set -euo pipefail
FLAGS=(-std=c++17 -O2)
if [[ ${1:-} = --checked ]]; then FLAGS+=(-DSBE_ENABLE_PRECEDENCE_CHECKS); shift; fi
for arg in "$@"; do
  case "$arg" in -std=*|-O*|-USBE_ENABLE_PRECEDENCE_CHECKS) echo 'INFRA: compile baseline cannot be overridden' >&2; exit 2;; esac
done
CXX=${CXX:-clang++}
if ! command -v "$CXX" >/dev/null; then CXX=g++; fi
command -v "$CXX" >/dev/null || { echo 'SETUP PROBLEM: install clang++ or g++' >&2; exit 2; }
exec "$CXX" "${FLAGS[@]}" "$@"
