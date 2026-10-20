# V0_demo03 formal batch audit

This CPU tool checks completed, real records without running Isaac Sim, opening an in-progress H5, changing labels, or training. It scans once and reports pending work; it does not poll. The executor saves `adjudication.json` and `execution_summary.json` after closing the collector. All three completion markers, including `independent_score.json`, must exist before this tool opens an episode.

Run from the LabSim repository, substituting the actual completed random batch root and a **new** output directory:

```bash
../labutopia-env/bin/python docs/lab_cuvette_loading/V0_demo03/data_audit/audit_formal_batches.py \
  --fixed-root outputs/lab_cuvette_loading/V0_demo03/fixed5_20261020_01 \
  --random-root outputs/lab_cuvette_loading/V0_demo03/RANDOM_BATCH_ROOT \
  --expected-fixed 5 --expected-random 10 \
  --output outputs/lab_cuvette_loading/V0_demo03/data_audit/NEW_FORMAL_AUDIT
```

It checks source/target IDs; preserved local rack/adapter geometry; recorded rigid assembly shifts; legal slot and safe initial pose; preflight coordinates; provenance-bound config snapshot; obs/action/next-state timestamps; state continuity; native/finite-difference channels; final H5 labels against the independent score and post-close adjudication; sidecar/raw hashes; and source H5 hashes before and after reading. Assembly checks compare saved config, computed layout, preflight and measured initial pose. They do not independently read composed USD transforms or cooked collision surfaces.

Action checks also stream the actual per-physics-step records with bounded memory, join each control endpoint, and verify the stored 8D action against the first eight commanded joints after the writer's float32 conversion. They check symmetric left/right commanded finger positions and verify that `agent_pose` is the measured first eight joints. Its eighth value is the actual left finger position, not the bilateral mean. Phase-dependent finger effort caps remain auxiliary controls in `physics_records.json`; a batch that can be read does not establish complete physical replay using only 8D joint targets. See `action_scope.md`.

`audit.json` includes per-episode checks and SHA256; `episodes.csv` gives the compact list. Workflow failure and malformed data are separate outcomes: a failed physical episode can have a valid schema and consistent false qualification. Missing/unknown qualification fields are rejected. Expected episode counts are explicit; missing future trials are not fabricated.

Two recording layers must remain distinct:

- `result.json` was saved before independent adjudication. Its `data_eligible=false`, `full_task_eligible=false` and native/full-result fields remain conservative provisional values. Final eligibility comes from the independent score, post-close adjudication and completed H5. The legacy `execution_summary.full_task_eligible` is also provisional; its `data_eligible` copies the independent score.
- `privileged/progress` is controller progress sampled when caching a transition. The final VERIFY decision occurs after the last cached transition. In actual dev_03, the last sampled `stable=false` is retained, while the independent final score measures a real 3.1 s post-retreat stable window. This does not justify filling the sampled bit with true. Final stability comes from actual physics evidence, and native/finite-difference disagreement remains a warning.

`native_pair_success=false` and `real_calibrated=false` are retained for adapted-mode successes. This audit validates the explicitly scoped simulated data contract; it does not certify OEM pairing or real accuracy.

Tool validation uses **existing actual records**, not fabricated episodes:

- `formal_audit_dev03_validation/`: one dev_03 actual complete workflow; audit passes, independent success and qualified H5 true. This is a one-episode tool check, not the formal fixed-five batch.
- `formal_audit_dev02_failure_validation/`: one dev_02 actual failure; audit passes data consistency, physical workflow false, eligibility false, post-retreat unavailable/stability null. The failure remains unchanged.
- `formal_audit_pure_checks.json`: pure success/failure/unknown-label counterexamples and pending-folder no-open guard. No fake H5 or physics trajectory was created.

The tool does not invoke the loader for every record. It reuses the existing `data_check.inspect_episode` qualification checks. The previously saved actual loader/batch evidence is `dev_03_actual_loader.json`, `dev_03_actual_batch_sample.json` and `sample_data/`. A new filtered index and existing-loader batch can be generated with `python -m demos.lab_cuvette_demo03.data_check --candidates CANDIDATES.json --output NEW_INDEX_DIRECTORY` once the formal batch is complete.
