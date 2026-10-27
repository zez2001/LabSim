# LabSim

LabSim provides a reproducible scientific robot manipulation environment in Isaac Sim. A Franka extracts a cuvette from a complete white 6×6 rack, transports it into one open instrument, places it in the original internal A seat, transfers support, opens the fingers, retreats, and observes stability for at least three seconds.

[中文主页](README.md) · [Developer onboarding](docs/development/ONBOARDING.md) · [Release acceptance](docs/lab_cuvette_loading/Project_release_v1/README.md) · [Assets](https://huggingface.co/datasets/Txie000/SLAI-Labsim)

## Demonstration and supported scope

The current release entry is **Project_release_v1**. It retains Project_v1_1 physics and scoring, with independent lifecycle, publication and recording changes. The same-process success–controlled finish–reset-success sequence and formal data reading are verified. The release qualification reader was fixed independently for the controlled-finish group without changing historical labels or success BC gates. A real π0.5 policy completed 69 inference calls and 341 actions before a safety-collision stop; its environment shutdown and data reads have also been checked. See the [actual release status](docs/lab_cuvette_loading/Project_release_v1/README.md).

[Watch a complete teacher episode](docs/lab_cuvette_loading/Project_release_v1/media/teacher_full.mp4). This is the first episode of the current release same-process acceptance run, continuously covering initialization through post-retreat stability. The teacher uses privileged task state. GPT has demonstrated stable grasping, extraction and transport, but has not completed loading independently.

The fixed standard scene uses `cuvette_xy_1000` (10×10×67.5 mm), an assumed mass of 20 g, source slot A1, a blue vessel in F6, one instrument, and the unchanged original A seat `candidate_far_hinge`. Physics is 240 Hz; control is 60 Hz. Scene randomization is off for collection and training. These are simulation assumptions, not real-world calibration.

Linux, Python 3.11, Isaac Sim 5.1.0 and RTX 4090 have been used for physical validation. Run Isaac processes sequentially on one GPU. Reuse an existing Isaac installation; LabSim does not automatically upgrade Isaac, Torch or model environments. Clean-checkout evidence is on the development machine, not a second computer.

## Install and first run

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --project-version Project_release_v1 --json

./labsim demo --project-version Project_release_v1 --sequence early_finish \
  --gui --record-mode eval --output outputs/lab_cuvette_loading/Project_release_v1/gui_001
```

Use an existing Python 3.11 with Isaac Sim 5.1 and task dependencies. Prepare geometry utilities in a separate environment as described in [onboarding](docs/development/ONBOARDING.md); do not install the entire historical requirements file into an existing Isaac or model environment. `doctor` is a CPU preflight, not a physical validation.

Assets are anonymously downloaded and SHA256-checked against revision [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067). The [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json) lists 83 dependencies: 82 HF files and a separately sourced Franka file. Cache defaults to `~/.cache/labsim/assets/<revision>/`; use `LABSIM_ASSET_CACHE` or a complete `LABSIM_ASSET_ROOT` tree when needed. HF login is not required.

The demo above is an actually tested short GUI startup, three-second controlled interaction and shutdown check, not complete teacher loading. Use headless mode without a display. Always select the version explicitly. Omitting `--project-version` still selects historical `Project_v1`. Every output directory must be new. A successful process exit is not a successful task: inspect results, independent score and video.

## Collect and read

```bash
export LABSIM_RUN=outputs/lab_cuvette_loading/Project_release_v1/collect_001
./labsim collect --project-version Project_release_v1 --headless --record-mode collect \
  --sequence teacher early_finish teacher --output "$LABSIM_RUN"

# Wait for the simulation process to close; build a new three-episode index.
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index \
  "$LABSIM_RUN" --output "$LABSIM_RUN/index/episode_data.hdf5"
./labsim dataset-check \
  --index "$LABSIM_RUN/index/episode_data.hdf5" \
  --sample-filter all_valid --policy both --output "$LABSIM_RUN/read_all_valid.json"
```

The same-process three-episode run actually completed teacher success, a three-second controlled finish, and teacher success after reset. Episode IDs are unique; stale actions were rejected with zero executed steps. Success/failure/all_valid index counts are 2/1/3; full H5 reads and 42 lower-level ACT/DP reader checks passed. After the independent release-reader fix, official dataset-check was rerun in a clean checkout for all three filters; both ACT and DP admitted 2/1/3 episodes respectively. Episode 2 retains its failure label. Record modes are explicit: collect and eval currently both persist complete H5/video and lossless-gzip physics streams; diagnostic retains plain logs and the extra collector video. Online scoring and safety rates do not change; eval is not an image-free lightweight mode. Comparable complete-episode output decreased from 3.878 GB to 2.327 GB (about 40%), without dropping H5 images. Rollout timing varied, so no reliable speedup is claimed.

The default index has relative HDF5 links. Move it together with every declared source H5, preserving the tree; the index alone is not a complete dataset. Add `--mode copy` explicitly for a self-contained index, with additional full-image storage. `all_valid` is for this three-episode reading check; success BC still uses `--sample-filter success`. Choose new paths for runs, indexes and read reports.

Episodes contain side/wrist RGB, robot state, requested and executed actions, timestamps, contacts, events and independent labels. A native complete H5 is about 1.95 GB and is not in small reading packages. Success BC admits only qualified complete successes; failures, service errors and control diagnostics retain separate labels. ACT/DP reading is verified; this release does not train models. Split by whole episode.

The [public sample](config/lab_cuvette_loading/Project_v1/public_samples.json) is earlier `Project_v1`, with 96-pixel images and the full time series, pinned to revision `82317fe33089aca5a20827da2adc592a1e0fdddc`. It is not native-resolution data from the current version.

## Policy evaluation and API

Teacher, Cubence `gpt-6-astra`, and external RPC clients share physics, bounded actions, recording and independent scoring. GPT08 is a genuine multi-round visual-policy episode that voluntarily ended after stable transport, with `task_success=false`. The current π0.5 run made 69 real inference calls, received 341 action receipts and advanced 17.017 seconds. The final action partially executed before ROBOT_ENVIRONMENT_COLLISION; task failure is separate from valid recording. All 69 inference waits preserved simulation time. It uses a LIBERO SFT checkpoint with explicit engineering action transfer, not LabSim training. Harness retains only its historical short connectivity evidence. See the [current external-policy contract](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md) and the [version guide](docs/lab_cuvette_loading/Project_v1_1/README.md) for actual inference and deployment requirements.

The public lifecycle is `reset / observe / execute / receipt / status / finish / close`. Physics pauses during inference and advances a defined number of steps per action. Episode and observation IDs reject stale requests; action IDs give idempotent receipts, including partial execution. `finish` requests independent scoring rather than accepting policy-provided success.

The [interface contract](docs/development/ONBOARDING.md#策略接口与时序) defines units, frames, limits and timing. End-effector actions use meters, radians, world/TCP frames and wxyz quaternions. Recorded 8-D ACT/DP actions are seven absolute joint targets plus one finger position; the executed symmetric 9-D command is also saved. Declared tactile feedback is the cuvette-filtered per-finger normal-force magnitude. `GenericContactHold` holds finger commands through physical contact without attaching the object. Credentials stay outside Git, logs and datasets.

The π0.5 source run also contains ten short reset resource probes. The generic failure/all_valid filter does not infer evaluation intent. Use the [curated model-only index](docs/lab_cuvette_loading/Project_release_v1/validation/pi05_standard_01_env_closed/curated_index_manifest.json): one real policy failure, not eleven policy evaluations.

## Help, sources and development

The short release GUI run exited 0 and did not reproduce the old menu `get_stage_state` exception. An SDK-extension `ManipulatorFactory` shutdown callback still raised a NameError in GUI and headless runs. Data and processes closed normally, but shutdown is not claimed to be error-free.

Missing Isaac/USD: select the installed Isaac Python and rerun `doctor --project-version Project_release_v1 --json`. Missing assets or hash mismatch: download pinned files instead of mixing revisions. Existing output: choose a new path. No display: use headless. A valid task failure can be a valid evaluation; environment, service and data errors are reported separately.

LabSim builds on [LabUtopia](https://github.com/Rui-li023/LabUtopia). See [upstream references](docs/upstream/README.labutopia.md), [LICENSE](LICENSE), and asset-specific sources in the [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json). The external instrument and cuvette CAD and derivatives are authorized for public redistribution. Franka remains at its fixed public source and was not reuploaded to HF. There is no real-world calibration, liquid simulation, glass fracture, spectral measurement or real-robot operation.

`codex/labsim` is the long-lived development and default GitHub branch; `main` retains the upstream baseline. Routine fixes stay on this branch. See [CONTRIBUTING](CONTRIBUTING.md), [onboarding](docs/development/ONBOARDING.md), [CPU CI](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml), [history](docs/history/README.md), and [result packaging](docs/agent_handoff/README.md).
