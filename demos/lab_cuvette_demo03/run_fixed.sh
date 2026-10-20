#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
BASE="${1:?Provide a new fixed-five output directory}"
mkdir "$BASE"
for i in 0 1 2 3 4; do
  bash demos/lab_cuvette_demo03/run.sh --headless --seed 0 --output "$BASE/fixed_$i"
done
"${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_demo03.summarize --roots "$BASE" --output "$BASE/summary"
