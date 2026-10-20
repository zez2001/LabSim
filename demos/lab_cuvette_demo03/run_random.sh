#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
BASE="${1:?Provide a new random-ten output directory}"
STANDARD="${2:?Provide the passed fixed-five summary episodes.json}"
"${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" - "$STANDARD" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]));c=m['counts']
assert c['executed']==5 and c['independent_workflow_success']==5 and c['independent_data_eligible']==5, 'Run random only after all five fixed workflows pass independent scoring'
PY
mkdir "$BASE"
for seed in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  bash demos/lab_cuvette_demo03/run.sh --headless --random-layout --seed "$seed" --output "$BASE/seed_$seed"
done
"${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_demo03.summarize --roots "$BASE" --output "$BASE/summary"
