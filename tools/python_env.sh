#!/bin/sh
# Shared interpreter selection; source only after setting ROOT to the repository.
if [ -z "${BOM_PYTHON:-}" ]; then
 if [ "${OS:-}" = Windows_NT ] && [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  BOM_PYTHON="$ROOT/.venv/Scripts/python.exe"
 elif [ -x "$ROOT/.venv/bin/python3" ]; then
  BOM_PYTHON="$ROOT/.venv/bin/python3"
 elif [ "${OS:-}" = Windows_NT ]; then
  BOM_PYTHON=python
 else
  BOM_PYTHON=python3
 fi
fi
export BOM_PYTHON
export PYTHONUTF8=1
"$BOM_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12+ required")' || exit 1
