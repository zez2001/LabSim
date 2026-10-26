# Project_v1 — teacher GUI example

`teacher_full_continuous.mp4` is one complete continuous run (105.83 s, 1280×480, 30 fps). Left: fixed scene camera. Right: wrist camera. No attempt stitching, time truncation, frame dropping, or playback speed changes. The existing stage/time overlay is preserved. “FINAL RESULT: SUCCESS” is the independent final verdict, not an intermediate-stage label.

`teacher_release_wrist_closeup.mp4` is the contiguous wrist-camera suffix from approximately 88.02 s through the end. Six PNGs are mapped to actual source-frame simulation timestamps in `media_manifest.json`.

This example used the 10×10×67.5 mm size-hypothesis vessel and the original A internal seat (`candidate_far_hinge`), in a fixed standard scene. It is not a validation of the original 12.5 mm combination or real calibrated precision. The teacher uses simulator truth.

Observed independently: source-slot clearance, held transport, internal loading/support, both fingers opened and detached, gripper retreat, and a full three-second post-retreat stable window. Warnings remain: native versus pose-difference velocity disagreement and unavailable cooked target overlap.

Source snapshot: `d09c5ffce2018702702eb0d4c77d862f1eae6faa`; source scene fingerprint: `75d288fe67e88c749cb578f36f3c246664b3e26d8455926bffbccf3576964de6`. This earlier GUI example is separate from later formal repetition snapshots. The manifest records source/output SHA256, exact frames, timestamps, event evidence, encoding parameters, and limitations.

## Separate GPT debug attempt

`gpt_pilot02_full_attempt.mp4` is the full continuous Cubence `gpt-6-astra` debug pilot to its actual collision stop: 267 frames, 8.9 s presentation time, final sampled simulation time 8.866667 s. Six API decisions produced five accepted movements/531 control ticks; one action was rejected by the protocol. The last accepted movement ran 0.85 s/51 ticks before the stop, despite a historical receipt field saying 2 s.

Final independent result: `PHYSICS_INVALID / ROBOT_ENVIRONMENT_COLLISION`, `task_success=null`, `record_valid=false`; no grasp or release occurred. This is a debug attempt, not a formal repeated result or a valid complete-task failure episode. `gpt_pilot02_media_manifest.json` records exact frame ranges, source/output hashes, controller/code/scene identity, corrected duration measurement, and the unavailable post-retreat window.

## Separate GPT debug pilot 03

`gpt_pilot03_full_attempt.mp4` preserves the full continuous 784-frame attempt (26.133 s presentation; final simulation timestamp 26.116667 s). Fourteen API decisions were accepted: thirteen `move_ee` motions and one gripper action, totaling 1,566 control ticks. Bilateral contact, lift, and source-slot clearance were observed, but stable grasp and transport did not pass. The relative bottom-frame pose drift was 26.837 mm (includes rotation lever-arm effects, not isolated axial slip).

Final independent result: `PHYSICS_INVALID`, with `actual_object_pose_jump_above_declared_limit` and a retained source-rack penetration quality flag; `task_success=null`, `record_valid=false`. No release or retreat occurred. This is a debug pilot and is separate from the formal five attempts.

The separate pilot03 manifest distinguishes canonical frozen controller SHA256 (`af223844...`) from the wrapper’s misleading `controller_sha256` field, which contains the `cubence_tools.py` source hash (`0e0af868...`), and from the controller file’s raw byte hash.

## Formal GPT fixed-standard five-attempt results

`gpt_formal04_of05_full_attempt.mp4` is the complete fourth formal attempt (`attempt_0003`): all 883 original frames through the 29.416667 s final simulation timestamp (29.433 s presentation). It is a valid `GRASP_SLIP` task failure (`task_success=false`, `record_valid=true`), selected because it contains actual bilateral contact, lift and source-slot clearance. Stable grasp/transport did not pass; no insertion, release or retreat occurred. A stable terminal window is not a post-retreat window.

`gpt_formal05_of05_final_physics_invalid.png` shows only the fifth attempt's actual final frame (32.35 s) as a collision/physical-invalid contrast; no second long video was added. The formal cohort has zero complete successes, one valid grasp-slip failure and four physics-invalid/unknown-outcome records. All five processes were closed before media processing. Debug pilots remain separate.

`gpt_formal5_media_manifest.json` records every attempt's final result, actual events, warnings, closed-process/source hashes, canonical controller identity, and the representative full-video transformation. Frozen canonical controller: `af223844...`; wrapper `controller_sha256` is instead the tools source hash `0e0af868...`.
