"""Physical preparation for a placement-only policy test; never policy actions."""

import json

import numpy as np

from demos.cell_assets.cameras import VideoRecorder
from demos.cell_assets.motion import Motion, sample_joints


def prepare(task):
    """Use the existing expert to grasp and stage the rack 6 cm above its target.

    Initialization has its own video/trace. The policy episode and model call
    counters start afterwards, and its goal explicitly excludes initial pickup.
    """
    from isaacsim.core.utils.types import ArticulationAction

    folder = task.episode_dir / "initialization"
    folder.mkdir()
    recorder = VideoRecorder(folder, task.views)
    motions = []
    for motion in task.motions:
        if motion.name == "place":
            end = round(0.6 * (len(motion.joints) - 1)) + 1
            motions.append(Motion("stage_above_target", 2.5, motion.joints[:end], motion.aperture))
            break
        motions.append(motion)
    start, steps, records = task.world.current_time, 0, []
    try:
        for motion in motions:
            for i in range(round(motion.duration / task.scene["dt"])):
                fraction = (i + 1) * task.scene["dt"] / motion.duration
                q = np.r_[
                    sample_joints(motion.joints, fraction * fraction * (3 - 2 * fraction)),
                    motion.aperture,
                    motion.aperture,
                ]
                task.robot.apply_action(ArticulationAction(joint_positions=q))
                task.world.step(render=False)
                steps += 1
                row = task.measure(q, motion.name, start)
                records.append(row)
                if steps % 4 == 0:
                    task.world.render()
                    recorder.write()
                if max(row["robot_device_force_n"], row["robot_table_force_n"]) > 1:
                    raise RuntimeError("Placement initialization had unintended robot contact")
        last = records[-1]
        height = last["position_m"][2] - task.targets["loaded"][2]
        if min(last["finger_force_n"]) <= 0.01 or not 0.04 < height < 0.08:
            raise RuntimeError(
                "Placement initialization did not establish a held rack above the target"
            )
        report = dict(
            controller="expert_initialization_only",
            counted_as_policy=False,
            physics_steps=steps,
            simulation_seconds=steps * task.scene["dt"],
            held_height_above_target_m=height,
            bilateral_contact_N=last["finger_force_n"],
            task_goal="lower to support, release, withdraw and remain stable",
        )
        (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    finally:
        recorder.close()
        (folder / "physics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    task.unit["initial_state"] = "placement-ready"
    task.unit["initial_grasp_contact_N"] = last["finger_force_n"]
    task.unit["goal"] = (
        "The gripper already holds the green rack above the target surface. "
        "Lower the rack gently onto the surface directly below it, release it only after it is supported, "
        "then lift the empty gripper at least 12 cm and leave the rack stable for 3 seconds. "
        "Do not drop the rack from above or move it away from the target."
    )
