#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
BASE="${1:?Provide a new output batch directory}"
mkdir "$BASE"
for i in 0 1 2 3 4; do
  bash demos/lab_cuvette_demo01/run.sh --headless \
    --config config/lab_cuvette_loading/V0_demo01/engineering_demo.yaml \
    --output "$BASE/fixed_$i"
  "${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_demo01.analyze "$BASE/fixed_$i/trial_00"
done
