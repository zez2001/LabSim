#!/usr/bin/env bash
set -euo pipefail
LABSIM_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export OMNI_KIT_ACCEPT_EULA=YES
cd "$LABSIM_ROOT"
exec "${LABSIM_PYTHON:-$LABSIM_ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_size_v1.run "$@"
