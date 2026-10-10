#!/bin/sh
# Windows/Git Bash and Linux share the same audit, test and compile runner.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. "$ROOT/tools/python_env.sh"
exec "$BOM_PYTHON" tools/run_tests.py
