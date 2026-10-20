#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export OMNI_KIT_ACCEPT_EULA=YES
cd "$ROOT"
exec "${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_env_v1.run "$@"
