# Project_v1 — teacher GUI example

`teacher_full_continuous.mp4` is one complete continuous run (105.83 s, 1280×480, 30 fps). Left: fixed scene camera. Right: wrist camera. No attempt stitching, time truncation, frame dropping, or playback speed changes. The existing stage/time overlay is preserved. “FINAL RESULT: SUCCESS” is the independent final verdict, not an intermediate-stage label.

`teacher_release_wrist_closeup.mp4` is the contiguous wrist-camera suffix from approximately 88.02 s through the end. Six PNGs are mapped to actual source-frame simulation timestamps in `media_manifest.json`.

This example used the 10×10×67.5 mm size-hypothesis vessel and the original A internal seat (`candidate_far_hinge`), in a fixed standard scene. It is not a validation of the original 12.5 mm combination or real calibrated precision. The teacher uses simulator truth.

Observed independently: source-slot clearance, held transport, internal loading/support, both fingers opened and detached, gripper retreat, and a full three-second post-retreat stable window. Warnings remain: native versus pose-difference velocity disagreement and unavailable cooked target overlap.

Source snapshot: `d09c5ffce2018702702eb0d4c77d862f1eae6faa`; source scene fingerprint: `75d288fe67e88c749cb578f36f3c246664b3e26d8455926bffbccf3576964de6`. This earlier GUI example is separate from later formal repetition snapshots. The manifest records source/output SHA256, exact frames, timestamps, event evidence, encoding parameters, and limitations.

## Separate GPT debug attempt

`gpt_pilot02_full_attempt.mp4` is the full continuous Cubence `gpt-6-astra` debug pilot to its actual collision stop: 267 frames, 8.9 s presentation time, final sampled simulation time 8.866667 s. Six API decisions produced five accepted movements/531 control ticks; one action was rejected by the protocol. The last accepted movement ran 0.85 s/51 ticks before the stop, despite a historical receipt field saying 2 s.

Final independent result: `PHYSICS_INVALID / ROBOT_ENVIRONMENT_COLLISION`, `task_success=null`, `record_valid=false`; no grasp or release occurred. This is a debug attempt, not a formal repeated result or a valid complete-task failure episode. `gpt_pilot02_media_manifest.json` records exact frame ranges, source/output hashes, controller/code/scene identity, corrected duration measurement, and the unavailable post-retreat window.
