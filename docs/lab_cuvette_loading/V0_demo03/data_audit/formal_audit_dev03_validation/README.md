# V0_demo03 completed-batch data audit

Read-only, one-shot CPU audit. No physics, raw H5 rewriting, training or synthetic trajectories.

- **raw_result**: result.json is saved before independent adjudication. Its data_eligible=false and full_task_eligible=false are conservative provisional fields, not the final H5 eligibility.
- **final_qualification**: independent_score.json, post-close adjudication.json and completed H5 qualification attributes determine adapted-scene eligibility. execution_summary.data_eligible copies the independent score; its legacy full_task_eligible remains provisional.
- **sampled_progress**: privileged/progress is controller progress at transition caching. Final VERIFY adjudication occurs after the last cached transition. A last sampled stable=false is preserved; final stability is independently measured from the actual post-retreat physics window, not filled into progress.
- **scope**: video_demo_adapted simulated workflow; native_pair_success=false and real_calibrated=false remain separate facts even for eligible success.
- **failure**: A physically failed episode can pass schema/timestamp/label-consistency checks while correctly remaining ineligible. Expected false qualification gates are not malformed-data errors.
- **geometry**: Assembly verification recomputes config layout and compares saved preflight plus actual initial pose. It is not an independent reread of composed USD/cooked PhysX surfaces or a proof of global collision accuracy.

`audit.json` retains every per-episode timestamp/label/assembly check and source H5 SHA; `episodes.csv` is compact. Actual failed workflow is counted separately from malformed data. Uncompleted trials are not opened. Native calibration and OEM pairing remain false.
