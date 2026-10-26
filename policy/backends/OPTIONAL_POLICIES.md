# Optional π0.5 and RPent Harness adapters

These adapters use the same `ProjectEnvironment`, original seat,10mm cuvette, recorder and independent scorer as teacher/GPT6. They are optional dependencies: LabSim does not install or upgrade RPent, RLinf, OpenPI, Torch or Isaac. The direct `gpt6` backend uses Cubence; the retained Harness planner uses the separately deployed RPent/Codex login and must be selected explicitly.

The read-only CPU inventory on2026‑10‑26 found RPent commit `0d72dfac1e75417564e220e31ba7e4b5d8e83665`, Python3.11.16, `rpent-openpi==0.2.2`, `rpent-rlinf==0.3.0`, Torch2.7.1 and `openai-codex==0.147.0`. The local LIBERO checkpoint exists:7,473,091,464-byte weights, SHA256 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`; normalization SHA256 `dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`. No environment/model service was listening on8097/8098 at inventory time. File presence and package inspection do not prove a new physical task run.

Historical Env_v1 evidence contains actual π0.5, Astra and Harness model-to-simulator runs of five actions each, only0.25seconds of policy execution. π0.5 made one model call, Harness five. All ended `POLICY_BUDGET`, with no complete loading attempt. Those records remain historical connectivity evidence, not current Project_v1 success rates.

## Explicit deployment paths

Set these to an existing deployment. No author-specific absolute path is embedded in the new adapter configuration:

```bash
export RPENT_REPO_ROOT=/path/to/rpent
export LABSIM_POLICY_PYTHON="$RPENT_REPO_ROOT/.venv/bin/python"
export LABSIM_PI05_CHECKPOINT=/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT
```

Reproduce the CPU inventory without loading a model:

```bash
python3 scripts/audit_lab_cuvette_external_policies.py \
  --hash-weights --output outputs/optional_policy_inventory_new.json
```

Start the environment in one terminal:

```bash
./labsim serve --output outputs/project_policy_rpc_01 --headless --port 8097
```

Start the existing checkpoint service in another terminal:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.pi05_server \
  --model-path "$LABSIM_PI05_CHECKPOINT" \
  --output outputs/project_pi05_service_01 \
  --host 127.0.0.1 --port 8098
```

Run a finite π0.5 connectivity attempt:

```bash
"$LABSIM_POLICY_PYTHON" -m policy.backends.rpent_compat \
  --backend pi05 \
  --env-endpoint http://127.0.0.1:8097 \
  --vla-endpoint http://127.0.0.1:8098 \
  --subtask loading --layout-mode standard \
  --max-model-requests 1 --max-actions 5 \
  --output outputs/project_pi05_attempt_01
```

This five-action command is deliberately a connectivity check; it cannot be reported as a complete task benchmark. Increase the explicit budgets for a later full policy evaluation. An unadapted LIBERO checkpoint is not a LabSim-trained policy and no task success is promised.

For the optional historical Harness route, use the same command with `--backend harness`, explicit planner/action budgets and `--codex-bin /path/to/existing/codex`. It exposes the real short VLA primitive and generic actions, without teacher macros. It is distinct from the direct Cubence controller and is not included in its HTTP/token/cost accounting. The wrapper does not edit global Codex configuration or authentication.

The checkpoint output remains LIBERO normalized OSC delta XYZ/rotation and gripper sign. The new transfer configuration is `config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml`:20Hz model actions,60Hz control, at most0.5mm translation and0.004rad rotation per axis. These conservative caps satisfy the shared facade's norm speed limits. They differ explicitly from the old Env_v1 transfer; the old0.25second records do not validate the new transfer. The original checkpoint hash and normalization semantics are verified by the existing audited service before accepting outputs. This is an engineering embodiment transfer, not calibrated LIBERO dynamics or LabSim fine-tuning.

## RPC safety and current validation scope

The loopback-only server accepts the deployed RPent `POST /call` JSON/ndarray wire format. Existing `env.reset/step/chunk_step/get_observation/render_camera/get_camera_meta/get_task_language/get_env_meta/finalize_episode` calls are translated into the public facade. Each action retains its episode/observation identity; a deterministic legacy action ID prevents replay after a lost HTTP response. Private task phases, teacher/debug calls and caller-supplied success labels are unavailable. The server dispatches physics/render work on Isaac's owner thread; waiting for model requests does not advance simulation.

CPU contracts verify bounded-facade routing, ndarray round trips, idempotency, standard-only reset and private-method rejection. New Project_v1 physical π0.5/Harness episodes must be recorded separately before claiming real integration or full-task results. The current inventory explicitly records `new_project_optional_backend_physics_run=false`; update evidence by adding a new result, not editing historical records.

Services close through the RPC `shutdown` lifecycle method. Do not kill a shared Isaac process or start a second simulation on the same GPU. The optional checkpoint may coexist with one simulation if memory permits; such coexistence is not an isolated performance measurement.

## New Project_v1 physical connectivity checks

On2026-10-26 the pinned original checkpoint and both adapters were actually run against the new public Project_v1 RPC. π0.5 made one predict request and executed five actions (15control ticks,0.25seconds); Harness made one planner invocation and five VLA predict requests, executing five actions (15ticks). Both finished with POLICY_BUDGET and did not complete loading. The model service and one Isaac process shared the GPU for these short connectivity checks; their timings are not isolated performance measurements. All observations, actions and independent task results were saved. The evidence is [optional_physics_regressions_actual.json](../../docs/lab_cuvette_loading/Project_v1/policy_evidence/optional_physics_regressions_actual.json). The earlier inventory remains an immutable snapshot from before these checks.
