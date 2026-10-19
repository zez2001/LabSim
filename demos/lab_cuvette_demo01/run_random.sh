#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
FIXED="${1:?Provide completed fixed-five directory}"
BASE="${2:?Provide a new random output directory}"
"${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" - "$FIXED" <<'PY'
from pathlib import Path
import sys,json
p=Path(sys.argv[1]);scores=[json.loads((p/f'fixed_{i}'/'trial_00/independent_score.json').read_text()) for i in range(5)]
assert all(s['workflow_success'] and s['controller_agrees'] for s in scores),'All five fixed workflows must independently pass before this small random check'
PY
mkdir "$BASE"
for seed in 7000 7001 7002; do
  bash demos/lab_cuvette_demo01/run.sh --headless --random-layout --seed "$seed" \
    --config config/lab_cuvette_loading/V0_demo01/engineering_demo.yaml \
    --output "$BASE/seed_$seed"
  "${LABSIM_PYTHON:-$ROOT/../labutopia-env/bin/python}" -m demos.lab_cuvette_demo01.analyze "$BASE/seed_$seed/trial_00"
done
