#!/usr/bin/env bash
set -euo pipefail
LABSIM_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export OMNI_KIT_ACCEPT_EULA=YES
exec "${LABSIM_PYTHON:-$LABSIM_ROOT/../labutopia-env/bin/python}" "$LABSIM_ROOT/demos/lab_cuvette_loading/run.py" "$@"
