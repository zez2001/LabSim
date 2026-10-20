#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo 'Usage: bash reproduce.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
cd /home/wujing/Desktop/vla/LabSim
audit_destination="$1"
audit_base=outputs/lab_cuvette_loading/V0_demo03
audit_args=(--fixed-root "$audit_base/fixed5_20261020_01")
for seed in 8000 8001 8002 8003 8004 8005 8006 8007; do
  audit_args+=(--random-seed-root "$audit_base/random10_20261020_01/seed_$seed")
done
for seed in 8008 8009; do
  audit_args+=(--random-seed-root "$audit_base/random_recovery_20261020_01/seed_$seed")
done
audit_args+=(--excluded-trial "$audit_base/random10_20261020_01/seed_8008/trial_00")
audit_args+=(--interruption-evidence "$audit_base/random10_20261020_01/seed_8008_interruption.json")
audit_args+=(--output "$audit_destination")
exec ../labutopia-env/bin/python docs/lab_cuvette_loading/V0_demo03/data_audit/audit_final15.py "${audit_args[@]}"
