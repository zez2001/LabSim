#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export OMNI_KIT_ACCEPT_EULA=YES
exec flock /tmp/labsim-V0_ext01-gpu.lock "${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" "$ROOT/demos/lab_cuvette_demo03/run.py" "$@"
