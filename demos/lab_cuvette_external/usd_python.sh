#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}"
USD_LIB="$ROOT/../labutopia-env/lib/python3.11/site-packages/isaacsim/extscache/omni.usd.libs-1.0.1+69cbf6ad.lx64.r.cp311"
PHYSX_SCHEMA="$ROOT/../labutopia-env/lib/python3.11/site-packages/isaacsim/extscache/omni.usd.schema.physx-107.3.26+107.3.3.lx64.r.cp311.u353"
export PYTHONPATH="$ROOT:$PHYSX_SCHEMA:$USD_LIB${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$PHYSX_SCHEMA/bin:$USD_LIB/bin:$ROOT/../labutopia-env/lib:$ROOT/../labutopia-env/lib/python3.11/site-packages/isaacsim/kit${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PXR_PLUGINPATH_NAME="$PHYSX_SCHEMA/plugins/PhysxSchema/resources${PXR_PLUGINPATH_NAME:+:$PXR_PLUGINPATH_NAME}"
exec "$PYTHON" "$@"
