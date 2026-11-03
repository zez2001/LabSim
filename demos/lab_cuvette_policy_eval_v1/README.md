# Frozen policy evaluation analysis

Run from the repository root after episode writers have closed:

```bash
python -m demos.lab_cuvette_policy_eval_v1.analysis trials.json --output NEW_RESULTS_DIR
python -m demos.lab_cuvette_policy_eval_v1.plots NEW_RESULTS_DIR/summary.json \
  --manifest trials.json --output NEW_FIGURES_DIR
```

The command produces `summary.json`, `episodes.json`, `groups.json`,
`episodes.csv` and `stage_rates.csv`. It refuses to reuse an output directory.
Source episodes are read only, including H5 bytes and original scorer labels.

The trial manifest binds explicit intent to each planned episode:

```json
{
  "schema": "labsim.policy_eval.trials.v1",
  "protocol_id": "a-frozen-protocol-id",
  "protocol_sha256": "sha256-of-the-frozen-protocol",
  "trials": [
    {
      "trial_id": "gpt_01",
      "group_id": "gpt6_direct",
      "paired_trial_id": "pi05_01",
      "purpose": "formal",
      "status": "completed",
      "episode_dir": "runs/gpt_01/episode_0000",
      "environment_valid": true,
      "task_evaluable": true,
      "cost_summary_path": "costs/gpt_01.json",
      "closure_receipt_path": "checks/gpt_01.json"
    },
    {
      "trial_id": "gpt_02",
      "group_id": "gpt6_direct",
      "purpose": "formal",
      "status": "unstarted",
      "unstarted_reason": "remaining authorized API budget"
    }
  ]
}
```

Paths resolve relative to the manifest. `progress_dir` optionally points at a
separate offline Progress v1.2 analysis of the same original episode. Formal
records require an explicit `purpose: formal`; `diagnostic` and `historical`
records remain visible but are excluded from formal group denominators. A
single actual episode cannot fill two formal trials. Started statuses are
`started`, `completed`, `interrupted`, and `failed`; `started: true` is also
supported. Planned and unstarted entries do not enter started denominators.

`environment_valid` and `task_evaluable` may be declared with references to
the verifier's evidence. When absent they are conservatively inferred from
original reset, geometry, record validity, and failure-domain fields; absent
evidence stays unknown. Task safety failures remain task-evaluable. Budget
and time caps are censored observations, retained in the started denominator.
An explicit `censored` and `censor_reason` can refine this classification.

A cost summary can provide numeric fields `model_calls`, `returned_actions`,
`executed_actions`, `inference_seconds`, `service_wait_seconds`, `retry_count`,
`wall_seconds`, `input_tokens`, `output_tokens`, `cost_usd`, `action_rejections`,
`action_clipped`, and `action_execution_errors`. Optional `latencies_s` and
`action_execution_durations_s` preserve per-call/per-action samples. Missing
measurements stay null. Include `measurement_scope` to identify whether wall
time includes initialization, recording export, and process cleanup.

The primary success denominator includes every started formal episode. The
task-evaluable subset and exclusions are reported separately. Wilson score
95% intervals include counts. Stage confirmations consume the entire append-only
event log, including finalize events; 50 mm held translation is separate from
arrival at the fixed pre-insertion region. Missing evidence is unknown.

Target errors apply only where actual Progress `entrance_region` and
`current_attempt_route` gates are both true. Effective insertion uses
`valid_insertion_progress`; raw source-rack axial projections are excluded
from valid depth. Drift uses the three original physical-rate attempt scopes.
Group continuous summaries first reduce each episode, then weight episodes
equally; long trajectories do not receive extra weight through frame pooling.

The analysis verifies source identities, recorded Progress hashes, monotonically
increasing and adjacent control transitions, event/summary timing, and event-only
attempt replay. The run's independent closure verifier remains responsible for
H5 structural validation, full video decoding and native process exit. Its
receipt is hashed and retained, rather than inferred from task success.

The optional plotting command uses Matplotlib with a noninteractive backend and
produces six English-label PNGs: stage rates and Wilson intervals, per-episode
farthest milestone, termination distribution, representative Progress curves,
applicable target metrics, and separate inference/wall-clock quantities. It
refuses to draw without started formal episodes. Up to four actual cases are
shown in full; for larger studies, a declared median-stage rule chooses typical
cases per group and adds success/failure examples if space permits. Selection,
episode IDs, input hashes and figure hashes are saved in `plots_manifest.json`.
