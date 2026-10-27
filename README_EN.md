# LabSim

LabSim provides a reproducible scientific robot manipulation environment in Isaac Sim. A Franka extracts a cuvette from a complete white 6×6 rack, transports it into one open instrument, places it in the original internal A seat, transfers support, opens the fingers, retreats, and observes stability for at least three seconds.

[中文主页](README.md) · [Developer onboarding](docs/development/ONBOARDING.md) · [Release acceptance](docs/lab_cuvette_loading/Project_release_v1/README.md) · [Assets](https://huggingface.co/datasets/Txie000/SLAI-Labsim)

## Demonstration and supported scope

The current release entry is **Project_release_v1**. It retains Project_v1_1 physics and scoring, with independent lifecycle, publication and recording changes. Pinned assets and a short GUI lifecycle are verified; the same-process three-episode run and continuous real external policy acceptance are still pending. See the [actual release status](docs/lab_cuvette_loading/Project_release_v1/README.md).

[Watch a complete teacher episode](docs/lab_cuvette_loading/Project_v1_1/media/teacher_support_align_01_full.mp4). This is one continuous physical run from initialization through post-retreat stability. The teacher uses privileged task state. GPT has demonstrated stable grasping, extraction and transport, but has not completed loading independently.

The fixed standard scene uses `cuvette_xy_1000` (10×10×67.5 mm), an assumed mass of 20 g, source slot A1, a blue vessel in F6, one instrument, and the unchanged original A seat `candidate_far_hinge`. Physics is 240 Hz; control is 60 Hz. Scene randomization is off for collection and training. These are simulation assumptions, not real-world calibration.

Linux, Python 3.11, Isaac Sim 5.1.0 and RTX 4090 have been used for physical validation. Run Isaac processes sequentially on one GPU. Reuse an existing Isaac installation; LabSim does not automatically upgrade Isaac, Torch or model environments. Clean-checkout evidence is on the development machine, not a second computer.

## Install and first run

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --json

./labsim demo --project-version Project_release_v1 --sequence early_finish \
  --gui --record-mode eval --output outputs/lab_cuvette_loading/Project_release_v1/gui_001
```

Use an existing Python 3.11 with Isaac Sim 5.1 and task dependencies. Prepare geometry utilities in a separate environment as described in [onboarding](docs/development/ONBOARDING.md); do not install the entire historical requirements file into an existing Isaac or model environment. `doctor` is a CPU preflight, not a physical validation.

Assets are anonymously downloaded and SHA256-checked against revision [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067). The [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json) lists 83 dependencies: 82 HF files and a separately sourced Franka file. Cache defaults to `~/.cache/labsim/assets/<revision>/`; use `LABSIM_ASSET_CACHE` or a complete `LABSIM_ASSET_ROOT` tree when needed. HF login is not required.

The demo above is an actually tested short GUI startup, three-second controlled interaction and shutdown check, not complete teacher loading. Use headless mode without a display. Always select the version explicitly. Omitting `--project-version` still selects historical `Project_v1`. Every output directory must be new. A successful process exit is not a successful task: inspect results, independent score and video.

## Collect and read

```bash
./labsim collect --project-version Project_release_v1 --headless --record-mode collect \
  --sequence teacher early_finish teacher \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_001

# Wait until the simulation process has completely closed.
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_release_v1/collect_001/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_001/read_success.json
```

The three-episode acceptance command is currently running; it must close before claiming success–early-finish–reset-success. Episode 2 retains its failure label. Record modes are explicit: collect and eval currently both persist complete H5/video and lossless-gzip physics streams; diagnostic retains plain logs and the extra collector video. Online scoring and safety rates do not change; eval is not an image-free lightweight mode.

Episodes contain side/wrist RGB, robot state, requested and executed actions, timestamps, contacts, events and independent labels. A native complete H5 is about 1.94 GB and is not in small reading packages. Success BC admits only qualified complete successes; failures, service errors and control diagnostics retain separate labels. ACT/DP reading is verified; this release does not train models. Split by whole episode.

The [public sample](config/lab_cuvette_loading/Project_v1/public_samples.json) is earlier `Project_v1`, with 96-pixel images and the full time series, pinned to revision `82317fe33089aca5a20827da2adc592a1e0fdddc`. It is not native-resolution data from the current version.

## Policy evaluation and API

Teacher, Cubence `gpt-6-astra`, and external RPC clients share physics, bounded actions, recording and independent scoring. GPT08 is a genuine multi-round visual-policy episode that voluntarily ended after stable transport, with `task_success=false`. Historical π0.5 and Harness checks ran only five actions / 0.25 seconds and are connectivity evidence, not complete task evaluation. See the [current external-policy contract](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md) and the [version guide](docs/lab_cuvette_loading/Project_v1_1/README.md) for actual inference and deployment requirements.

The public lifecycle is `reset / observe / execute / receipt / status / finish / close`. Physics pauses during inference and advances a defined number of steps per action. Episode and observation IDs reject stale requests; action IDs give idempotent receipts, including partial execution. `finish` requests independent scoring rather than accepting policy-provided success.

The [interface contract](docs/development/ONBOARDING.md#策略接口与时序) defines units, frames, limits and timing. End-effector actions use meters, radians, world/TCP frames and wxyz quaternions. Recorded 8-D ACT/DP actions are seven absolute joint targets plus one finger position; the executed symmetric 9-D command is also saved. Declared tactile feedback is the cuvette-filtered per-finger normal-force magnitude. `GenericContactHold` holds finger commands through physical contact without attaching the object. Credentials stay outside Git, logs and datasets.

## Help, sources and development

The short release GUI run exited 0 and did not reproduce the old menu `get_stage_state` exception. A separate installed-extension `ManipulatorFactory` shutdown callback still raised a NameError, so GUI shutdown is not claimed to be error-free.

Missing Isaac/USD: select the installed Isaac Python and rerun `doctor --json`. Missing assets or hash mismatch: download pinned files instead of mixing revisions. Existing output: choose a new path. No display: use headless. A valid task failure can be a valid evaluation; environment, service and data errors are reported separately.

LabSim builds on [LabUtopia](https://github.com/Rui-li023/LabUtopia). See [upstream references](docs/upstream/README.labutopia.md), [LICENSE](LICENSE), and asset-specific sources in the [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json). The external instrument and cuvette CAD and derivatives are authorized for public redistribution. Franka remains at its fixed public source and was not reuploaded to HF. There is no real-world calibration, liquid simulation, glass fracture, spectral measurement or real-robot operation.

`codex/labsim` is the long-lived development and default GitHub branch; `main` retains the upstream baseline. Routine fixes stay on this branch. See [CONTRIBUTING](CONTRIBUTING.md), [onboarding](docs/development/ONBOARDING.md), [CPU CI](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml), [history](docs/history/README.md), and [result packaging](docs/agent_handoff/README.md).
