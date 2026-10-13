#!/usr/bin/env bash
set -euo pipefail
LABSIM_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABSIM_PYTHON="${LABSIM_PYTHON:-$LABSIM_ROOT/../labutopia-env/bin/python}"
export OMNI_KIT_ACCEPT_EULA=YES
exec "$LABSIM_PYTHON" "$LABSIM_ROOT/demos/minimal_precision_insertion/run.py" "$@"
