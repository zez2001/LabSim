# Run from the LabSim repository. Select the existing Isaac Python first.
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --project-version Project_release_v1 --json

./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration \
  --output outputs/lab_cuvette_loading/Project_release_v1/demo_NEW

export LABSIM_RUN=outputs/lab_cuvette_loading/Project_release_v1/collect_NEW
./labsim collect --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode collect --record-purpose demonstration --output "$LABSIM_RUN"
# After the Isaac process exits:
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose demonstration --output "$LABSIM_RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/index/demonstrations.hdf5" \
  --sample-filter success --policy both --output "$LABSIM_RUN/read_success.json"
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.transfer \
  "$LABSIM_RUN/index/demonstrations.hdf5" --verify-sha256 \
  --output "$LABSIM_RUN/dependencies.json"

./labsim eval --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/eval_NEW
./labsim serve --project-version Project_release_v1 --headless --port 8097 \
  --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/rpc_NEW
