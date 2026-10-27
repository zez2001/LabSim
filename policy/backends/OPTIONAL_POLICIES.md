# Optional π0.5 and RPent Harness backends

The current environment is **`Project_release_v1`**. Optional policies use the same fixed standard scene, original internal A seat, 10 mm cuvette, public execution interface, recorder and independent scorer as the Teacher. Start with the [current guide](../../docs/lab_cuvette_loading/Project_release_v1/README.md); the complete observation/action contract is [here](../../docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md).

| Backend | Function | Typical use |
|---|---|---|
| π0.5 | Real checkpoint inference over local RPC, action receipts, bounded execution, safety termination and normal data reading | Evaluate an existing LIBERO checkpoint on LabSim through the declared embodiment transfer |
| Harness | Local RPent planner/RPC route and recorded short policy calls | Connect an existing Harness deployment through the public environment lifecycle |
| Own policy | `reset`, public observation, `step`/`chunk_step`, receipts, `finalize_episode`, `shutdown` | Connect a local policy while retaining the same recording and independent scoring |

RPent, RLinf, OpenPI and the checkpoint run in an **existing separate policy Python**. LabSim leaves the Isaac and model environments unchanged. The direct GPT backend uses its separately configured provider; the optional Harness route uses its existing RPent/Codex deployment.

## Existing deployment

```bash
export RPENT_REPO_ROOT=/path/to/rpent
export LABSIM_POLICY_PYTHON="$RPENT_REPO_ROOT/.venv/bin/python"
export LABSIM_PI05_CHECKPOINT=/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT
```

The configured checkpoint is `RLinf-Pi05-LIBERO-130-fullshot-SFT`, with weight SHA256 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683` and normalization SHA256 `dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`. The audited service and client check these identities.

The [CPU inventory command](../../scripts/audit_lab_cuvette_external_policies.py) inspects the existing deployment without loading a model:

```bash
python3 scripts/audit_lab_cuvette_external_policies.py \
  --hash-weights --output outputs/optional_policy_inventory_NEW.json
```

## Run a finite policy evaluation

Start one environment and one model service in separate terminals, then run the client. Use a fresh output directory for every process:

```bash
./labsim serve --project-version Project_release_v1 --headless --record-mode eval \
  --record-purpose policy_evaluation \
  --port 8097 --output outputs/lab_cuvette_loading/Project_release_v1/pi05_env_NEW
```

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.pi05_server \
  --model-path "$LABSIM_PI05_CHECKPOINT" \
  --host 127.0.0.1 --port 8098 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_model_NEW
```

```bash
"$LABSIM_POLICY_PYTHON" -m policy.backends.rpent_compat --backend pi05 \
  --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
  --subtask loading --layout-mode standard \
  --max-simulation-s 20 --max-model-requests 80 --max-actions 400 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_policy_NEW
```

The budgets bound this evaluation. The full loading result comes from the environment scorer; client budget completion and model inference are separate results. The model is LIBERO-finetuned and used zero-shot on LabSim.

For Harness, select `--backend harness`, an existing `--codex-bin /path/to/codex`, and explicit planner/action budgets. It exposes the deployed short VLA primitive and public robot actions. It uses its own deployed model authentication and does not modify global Codex settings. Historical Harness connectivity evidence is linked below.

Services close through their RPC `shutdown` method. Wait for completion markers and actual process exit before indexing results. A model and one simulation may share a GPU for policy evaluation; run Teacher performance measurements separately.

## Observation and action contract

Public side/wrist observations are **HWC RGB `uint8 [480,640,3]`**. The RPent client adds a batch dimension; the model service receives **`[1,480,640,3]`**. The installed checkpoint processor uses PIL bilinear aspect-preserving resize/padding to 224×224, followed by float normalization and channel-first tensor conversion. The H5/ACT/DP branch separately stores 256×256 CHW images; it is not an intermediate step in this RPC path. See the [three-layer image table and actual-input audit](../../docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md#图像环境训练数据和-checkpoint-三层接口).

The checkpoint state is 8D: robot-base TCP position/rotation-vector and signed finger positions. The service applies the checkpoint quantile statistics. Current task text is 264 tokens under the deployed tokenizer and is truncated to its 200-token limit; the input audit preserves the effective IDs, mask and decoded prefix. [Local preflight and evidence](../../docs/lab_cuvette_loading/Project_release_v1/internal_use/20261028/input_audit/README.md) use the deployed tokenizer/processor without loading weights or starting a rollout.

The [existing transfer configuration](../../config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml) runs model actions at 20 Hz with 60 Hz control. It maps the first six LIBERO OSC values to bounded world-frame TCP deltas (0.5 mm / 0.004 rad per axis) and the seventh to stateful gripper opening, with an 8 N limit. The configuration's `Project_v1` directory is a compatibility path; the commands explicitly route to the current environment. All requests retain episode/observation identity and actual execution receipts. This round changes input observability and documentation while retaining pixel, state and action conversion values.

## Protocol and evidence

The loopback server supports `env.reset`, `env.step`, `env.chunk_step`, `env.get_observation`, camera/meta/language methods, `env.finalize_episode` and `shutdown`, using the RPent `POST /call` ndarray wire protocol. Physics and rendering execute on Isaac's owner thread. Model wait time does not advance simulation. Complete repeated chunks return cached original receipts; interrupted partial chunks are not resumed automatically.

Current release evidence: [69 real model calls and 341 acknowledged actions](../../docs/lab_cuvette_loading/Project_release_v1/external_policy/pi05_standard_01_closed_audit/summary.json), [normal reader validation](../../docs/lab_cuvette_loading/Project_release_v1/validation/official_pi05_dataset_check_clean_4a71635/failure.json). The task ended at a recorded safety collision. Earlier π0.5 and Harness five-action checks remain [historical connectivity records](../../docs/lab_cuvette_loading/Project_v1/policy_evidence/optional_physics_regressions_actual.json); their original labels and short durations are preserved.
