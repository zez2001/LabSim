# Teacher v7: alignment-preserving support transfer

Status: implemented and CPU-tested; the v7 physical loading experiment has not been run by this change. The closed v6 `teacher_baseline_close_01` remains a task failure (`TASK_INCOMPLETE`), despite observed release, retreat and a stable post-retreat window. Its independent `correct_target_supported` event was absent. The controller's earlier support predicate did not require the independent scorer's tighter alignment budget.

## Change and scope

Only `LabCuvetteProjectV11Teacher`'s `SUPPORT_TRANSFER` behavior changes. The v6 grasp/transport behavior, the original parent controller, shared gripper helper, assets, physics and independent scorer remain unchanged. `standard.yaml` changes only its two teacher-version labels to v7.

During support transfer the teacher now calls the parent's existing bounded XY and orientation feedback toward the original target floor and desired cup orientation. The existing per-step limits are retained (standard: 20 µm XY and 0.1° orientation). The parent still owns the original vertical force-relief equation; this change adds no resumed downward motion.

Unloading uses a separate monotone clock. It advances only over an observation interval whose previous and current actual-state alignment checks both pass. Otherwise it pauses the existing effort/opening schedule at its current fraction, while bounded alignment feedback continues. A restored valid sample first confirms alignment; the following valid sample resumes the clock. Pausing never rewinds the schedule or raises its effort limit. The original 3 s active-unload formula remains `effort = 8 - 7.95*fraction` and `opening = latch + (contact-latch)*fraction`.

The checks use the scorer's **same** quantities, defaults and configured values: Euclidean XY error ≤ `control.alignment_budget_m` (100 µm), absolute tilt ≤ `control.tilt_budget_deg` (0.15°), absolute yaw error ≤ `control.yaw_budget_deg` (0.2°). No per-axis substitute is used. Missing or nonfinite alignment measurements pause unloading.

`OPEN` requires completion of the active unloading interval, current/consecutive valid alignment, the parent's actual support predicate and its actual 0.5 s quiet window together. A completed ramp cannot bypass a later alignment violation. Target containment, actual loading depth, release, retreat and final task-success labels remain owned by the unchanged independent scorer.

The parent's local `u` is temporarily mapped only for its unloading formula. History timestamps, quiet windows, global timeout and events retain actual simulation time. Because the parent also uses `u` for its local watchdog, v7 explicitly retains the original strict **physical phase elapsed >10 s** failure condition. That condition vetoes a late `OPEN` and returns the current unloading command with a stop suggestion; it does not restore the initial 8 N cap. Normal transition to `OPEN` keeps its actual physical start timestamp.

## Data and boundaries

Action metadata records measured alignment, unchanged budgets, pause reasons, active unload time, physical phase time, and the 10 s watchdog. Duplicate observations return the existing cached action before changing feedback or either clock. Reset clears support-transfer state. The parent's quaternion alias remains supported.

This is an explicitly **truth-teacher** controller: alignment uses private actual object pose. It is not called by the GPT tool controller and does not add private coordinates or teacher stages to model observations. It assigns no task-success label. CPU semantics do not establish physical loading success or real calibration.

## Actual CPU verification

The focused teacher selection passed **127 tests**. The complete current CI contract selection then passed **578 tests, with 11 dependency skips and zero failures**. No source file changed during that run. The new support tests are included by the existing `tests/test_lab_cuvette_project_v1_1_*.py` workflow glob; no workflow modification is needed.

Evidence: [contracts result](validation/teacher_support_transfer_v7_final_20261027/contracts_result.json), [complete log](validation/teacher_support_transfer_v7_final_20261027/contracts.log), [JUnit](validation/teacher_support_transfer_v7_final_20261027/contracts_junit.xml). These are CPU software checks, with GPU and provider calls disabled.

Reproduce the new focused contract:

```bash
CUDA_VISIBLE_DEVICES='' PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_lab_cuvette_project_v1_1_teacher_support_transfer.py
```

Coverage includes pause/resume at irregular real intervals; bounded pose feedback while paused; monotone effort/opening; same norm, signed angle boundaries and unavailable signals; simultaneous `OPEN` gates; completed-ramp late misalignment; insert-to-support clock initialization; unscaled quiet/global/10 s watchdogs; quaternion alias; duplicate/reset; and unchanged non-support predicates. Two pre-existing assertions were narrowly updated because support commands now intentionally differ from the parent and can apply orientation feedback. Assertions for every other phase remain intact.
