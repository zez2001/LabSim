# Closed-trace control diagnostic

`closed_trace_probe` is an offline diagnostic launcher. It reuses the native
standard task, its unchanged physics and independent scorer, `ManualProbe`, and
the same `ProjectV11RobotTools` executor. It does not call an API, select a path,
read object truth for control, recover automatically, or become a tool available
to GPT. A diagnostic replay is not another GPT attempt or a demonstration.

Run these commands from the repository root using the existing Isaac Python.
They leave the closed source episode unchanged and refuse an existing output.
An output must be a new direct child of this checkout's
`outputs/lab_cuvette_loading/Project_v1_1` directory, or the equivalent version
base identified by the verified source process proof. This also permits a clean
checkout to write a new sibling run beside the original checkout's evidence.
Nested writes into any old run, other versions/assets, parent traversal and
symlink output components are refused before writing or starting Isaac.

```bash
export LABSIM_PYTHON=/home/wujing/Desktop/vla/labutopia-env/bin/python

"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.closed_trace_probe \
  --source outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control/policy_trace.jsonl \
  --proof outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/process_exit.json \
  --dry-run

"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.closed_trace_probe \
  --source outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control/policy_trace.jsonl \
  --proof outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/process_exit.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/closed_trace_original_01 \
  --headless
```

The default attempts the whole recorded list. In GPT05 this is 25 commands,
including the final error-row `model_tool_calls` move of world X +35 mm over
2 seconds. The original move requested 120 control ticks; its observed 114-tick
partial execution is evidence, not a replacement 1.9-second command. The new
execution uses the same requested parameters and retains its own actual receipt.
It stops on the first error, partial/safety stop, rejected move, unreached target,
or ended episode. No action is blindly retried.

`--dry-run` validates source evidence and prints the derived plan without
creating an output directory or importing Isaac. The process proof must name the
exact source run and runtime commit, contain an explicit integer exit code, and
declare process exit. The source PID must currently be absent; even a reused PID
is refused. A nonzero source exit code is preserved and disclosed rather than
silently treated as zero. Episode, result, metadata, options, action limits,
scene fingerprint, asset identity and audit asset hashes must agree. All
consumed files, including every trace-referenced public observation and image,
are SHA256 checked and copied into the new output. The original full trace is
always retained, even when only a prefix is replayed.

Before robot actions, the current resolved configuration and geometry audit,
then the actual reset contract and release metadata, must match the source scene
fingerprint and asset SHA. The new run manifest records the launcher, shared
helper and public-limit file hashes, exact current commit, reset seed and the
verified source identity. The parent supervisor must write authoritative
process-exit evidence after `Popen.wait()`; the child does not claim its own PID
has disappeared.

## Declaring a manual collision control

An intervention requires both `--prefix-actions N` and `--suffix-plan FILE`.
`N` counts recorded tool commands, starting at zero. The suffix explicitly lists
generic `move_ee`, `gripper`, `wait` or `observe` calls. There are no computed
waypoints, searches, target coordinates or automatic repair. For example, this
JSON declares two manual moves; it is a hypothesis to test, not a certified safe
route or a complete loading plan:

```json
{
  "schema": "labsim.Project_v1_1.closed_trace_suffix.v1",
  "description": "Manual raised-height control for the final lateral collision",
  "actions": [
    {
      "tool": "move_ee",
      "arguments": {
        "mode": "ee_delta",
        "values": [0, 0, 0.02, 0, 0, 0],
        "frame": "world",
        "duration_s": 2
      }
    },
    {
      "tool": "move_ee",
      "arguments": {
        "mode": "ee_delta",
        "values": [0.035, 0, 0, 0, 0, 0],
        "frame": "world",
        "duration_s": 2
      }
    }
  ]
}
```

Append `--prefix-actions 24 --suffix-plan /path/to/declared_control.json` to
the command and choose a new output directory. Run `--dry-run` first. The plan
hash, full original trace hash, suffix file hash, original decision/line indexes,
and original versus new IDs are written into the diagnostic receipts. Only
`episode_id`, `observation_id` and `action_id` are rebound by `ManualProbe`.
Other source parameters remain unchanged. The real GenericTools still enforces
its normal action bounds and runtime collision checks.

## Data and result interpretation

The ordinary collector records the new physical run and videos. Original
`task_success`, `record_valid` and independent physical scoring are not rewritten.
The run uses `condition_group: control_diagnostic`. The existing normal
`LabCuvetteProjectV11Dataset` rejects this group for both success and failure
training filters; this output is excluded from complete-task training. A physical
collision reproduced by the script can therefore have a zero launcher exit code
while its independent task result remains failure. A launcher/setup exception
retains a nonzero process code and `runner_failure.json` evidence.

CPU fixtures check unchanged source parameters, new IDs through the real
ManualProbe/GenericTools adapter, the final partial error-row command, explicit
suffix semantics, source corruption/closure/identity refusal, runtime contract
mismatch, shutdown and normal-reader rejection. These tests and dry-run do not
validate a physical replay. Actual GPU replay results must be reported separately.
