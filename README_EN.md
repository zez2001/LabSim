# LabSim

LabSim provides complete physical tasks, standard demonstration collection, and a unified policy evaluation interface for scientific robot manipulation in Isaac Sim. In `lab_cuvette_loading`, a Franka grasps a cuvette from a complete white 6×6 rack, extracts and transports it into an open instrument's internal A seat, inserts it, transfers support, opens and separates the fingers, retreats, and observes stability for at least three seconds.

The recommended version is **`Project_release_v1`**, on the long-lived **`codex/labsim`** branch.

[中文主页](README.md) · [Internal usage guide](docs/development/ONBOARDING.md) · [Version and technical reference](docs/lab_cuvette_loading/Project_release_v1/README.md) · [Public assets](https://huggingface.co/datasets/Txie000/SLAI-Labsim)

## Complete demonstration

[![Continuous cuvette loading](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/scene.png)](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/teacher_full.mp4)

[Watch a continuous complete Teacher episode](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/teacher_full.mp4), from the rack initial state through post-retreat stability. Teacher uses privileged task state for physical grasping and loading. Policy-specific capabilities are listed below.

## Supported tasks

Single-cell units are a parallel extension with bounded mechanical operations for five instruments, including derived PCR wells. See [single-cell units](demos/cell_units/README.md) and use `./labsim unit list` to list them. Expert recordings and limited policy calls are reported separately; they do not establish a complete single-cell experiment or real-world calibration.

[Asset APIs and demos](demos/cell_assets/README.md) retain pinned sources, Franka contact demonstrations and scope limits. [Public source assets and licensing](docs/cell_assets/HuggingFace上传指南.md) describe the HF mirror and unpublished derivatives; historical outcomes are in the [unified results index](docs/history/RESULTS.md).

| Module | Function | Typical use |
|---|---|---|
| Assets and standard scene | Franka, complete 6×6 rack, one open instrument, internal A seat, registered size variants and provenance | Fixed-scene manipulation and size studies |
| Physical task | Grasp, extract, transport, insert, transfer support, slowly release, separate, retreat and check stability | End-to-end demonstrations and stage analysis |
| Fine execution | End-effector/joint actions, continuous IK, actual-state tracking, bounded execution, idempotent receipts and error diagnostics | Policy integration and empty-gripper simulation TCP measurements |
| Recording | Two RGB views, robot state, requested/executed actions, successor states, contacts, events and timestamps | ACT/DP data reading and failure analysis |
| Independent evaluation | Stage progress, full success, termination reason, record integrity, physics quality and data qualification | Policy comparisons and demonstration filtering |
| Project interfaces | Unified CLI, Teacher, direct GPT control, π0.5 RPC, Harness and custom-policy lifecycle | Internal reuse and external policy evaluation |

Demonstrations and training-data preparation use fixed `standard`. The evaluation interface can explicitly select ten fixed candidate `random_001`–`random_010` instances; see the [scene protocol](docs/lab_cuvette_loading/Scene_suite_v1/README.md) for definitions, allowed uses and physical acceptance status. See [asset and physics specifications](docs/lab_cuvette_loading/Project_release_v1/README.md#资产与物理规格) for dimensions, mass, rates and pending measurements. This is rigid-body simulation with engineering assumptions for mass, friction and dynamics. A complete Teacher demonstration does not establish completion by another policy.

## Installation and assets

Use Linux, Python 3.11 and Isaac Sim 5.1.0. Prepare an existing Isaac interpreter and separate geometry tools using [onboarding](docs/development/ONBOARDING.md#准备环境与资产). Hardware validation records, workspace layout and deployment checks are in [deployment and delivery](DELIVERY.md).

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --project-version Project_release_v1 --json
```

Assets are downloaded anonymously and checked against the [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json), pinned to HF revision [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067). Of 83 dependencies, 82 come from HF and Franka comes from a pinned public source. The default cache is `~/.cache/labsim/assets/<revision>/`; override it with `LABSIM_ASSET_CACHE` or a complete `LABSIM_ASSET_ROOT`.

## Complete-task quick start

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration \
  --output outputs/lab_cuvette_loading/Project_release_v1/demo_001
```

This is the ordinary complete-task entry. Replace `--gui` with `--headless` without a desktop; choose a new output directory. Startup displays the resolved version, task, scene, policy, asset, configuration/scene fingerprints, recording mode, purpose and output path. Inspect `episode_0000/result.json`, the independent score, `dual_view.mp4` and final qualification. A complete task takes about 126 simulation seconds; image recording increases wall time.

`--project-version current` is an alias whose records contain the resolved `Project_release_v1`. Omitting the option retains the historical `Project_v1` default. Three-second installation checks and mixed lifecycle sequences are documented under [development acceptance](docs/development/ONBOARDING.md#安装检查与生命周期验收).

## Standard collection and reading

```bash
export LABSIM_RUN=outputs/lab_cuvette_loading/Project_release_v1/collect_001
./labsim collect --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode collect --record-purpose demonstration --output "$LABSIM_RUN"

# Run after the collection process exits.
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose demonstration --output "$LABSIM_RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/index/demonstrations.hdf5" \
  --sample-filter success --policy both --output "$LABSIM_RUN/read_success.json"
```

Purpose and qualification are independent: `demonstration` selects the cohort; `success` selects qualified complete successes. Normal ACT/DP readers load an actual batch. Action formats and the rule for splitting training and validation by complete episode are in the [data contract](docs/lab_cuvette_loading/Project_release_v1/data_usage.md).

The default `relative-links` index must move with its source H5 files, preserving relative paths. `--mode copy` creates a self-contained file while preserving image hardlink aliases. See [data usage and transfer](docs/lab_cuvette_loading/Project_release_v1/data_usage.md) for historical sidecars, qualifications and dependency checks. Both `collect` and `eval` recording modes retain full H5, native video and compressed physics logs; `diagnostic` also retains detailed logs. Recording mode and purpose are separate options.

## Policy integration and evaluation

| Policy | Capability | Entry |
|---|---|---|
| Teacher | Complete physical loading demonstrations | `demo` / `collect --backend teacher` |
| Direct GPT control | Image/state tool calls, budget management and execution receipts | `eval --backend gpt6`, separate credentials and budget |
| π0.5 | Model RPC, action adapters, execution receipts, safety termination and data readback | Environment `serve`, model service and adapter client |
| Harness | Local RPC client and a shared environment lifecycle | `serve` and Harness client |
| ACT / DP | Normal dataset readers and actual batch loading | `dataset-check --policy both` |
| Custom policy | Unified observation, execution and lifecycle | `reset / observe / execute / receipt / status / finish / close` |

```bash
# Teacher evaluation; evaluation and demonstration cohorts use separate indexes.
./labsim eval --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/eval_001

# One fixed evaluation scene; repeated runs load the same definition.
./labsim eval --project-version Project_release_v1 --scene random_003 \
  --backend teacher --headless --episodes 1 --progress \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/random003_001

# Ten fixed scenes, one repetition each; sequential execution on one GPU.
./labsim eval --project-version Project_release_v1 --suite random10 \
  --episodes-per-scene 1 --backend teacher --headless --progress \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/random10_001

# Start the environment, then connect a policy client from another terminal.
./labsim serve --project-version Project_release_v1 --headless --port 8097 \
  --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/rpc_001
```

Public observations include both cameras, robot state and declared contact signals. Simulation pauses during model inference. Action frames, units, limits and receipts are in the [interface guide](docs/development/ONBOARDING.md#策略接口与时序). Image processing, task-text/tokenizer truncation and deployment input audits are in the [external-policy contract](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md). Actual policy results and unexecuted scope are collected in the [results index](docs/history/RESULTS.md).

## Documentation, sources and license

- [Internal usage guide](docs/development/ONBOARDING.md): environment → complete task → collection → reading → policy integration, troubleshooting and implementation map.
- [Current technical reference](docs/lab_cuvette_loading/Project_release_v1/README.md): assets, interfaces and acceptance evidence.
- [Unified results index](docs/history/RESULTS.md): Progress, policy evaluation, historical restoration, cell units and milestone evidence, each with its own denominators and unexecuted scope.
- [Data usage and transfer](docs/lab_cuvette_loading/Project_release_v1/data_usage.md) · [Optional policy deployment](policy/backends/OPTIONAL_POLICIES.md).
- [History](docs/history/README.md) · [Contributing](CONTRIBUTING.md) · [CPU CI](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) · [Result packages](docs/agent_handoff/README.md).

LabSim builds on [LabUtopia](https://github.com/Rui-li023/LabUtopia); see [upstream references](docs/upstream/README.labutopia.md) and [LICENSE](LICENSE). Asset-specific provenance and authorization are recorded in the [lock file](config/lab_cuvette_loading/Project_v1/assets.lock.json). The project owner authorized public redistribution of the external instrument/cuvette CAD and derivatives. This is rigid-body simulation; real-world mass, friction and dynamics remain engineering assumptions pending calibration.
