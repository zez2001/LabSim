# Closed termination lifecycle checks

The five cases ran in one native Isaac process using source `73b1a9d`. Both native and supervisor processes exited with code 0 before this read-only CPU audit. `summary.json`, `checks.json`, `episodes.csv`, and `videos.json` contain the targeted checks and exact qualifications.

`early_finish`, `no_progress`, and `unreachable` are valid task-failure lifecycle records. `service_timeout` and `user_interrupt` are explicit injected termination domains: their task outcome is unknown, and their records are excluded by the normal task failure/all-valid filters. They do not prove a real service outage or actual user key event. No case completed the loading task, and this diagnostic cohort adds no trajectories to the complete-task collection quota.

All 15 MP4 streams were decoded to EOF. H5 checks cover final labels, transactional identity, state/action time alignment, terminal successor, and image shapes; the audit does not reread every H5 image pixel or all physical traces. The legacy embedded independent score is a pre-close snapshot, while final publication fields include collector integrity; its SHA binds the embedded bytes, not the separately rewritten final independent-score file.

Source evidence was hashed before and after the audit and never modified. Run `audit.py` with the native Python only after choosing a new output directory, because it refuses to overwrite this audit.
