# 公开 TCP—手掌固定几何审查

实际 GPT03 输入（runtime `109e637bcb264458ffc231f4e052e60ff6764242`）**没有直接声明** `TCPpose` 对应 `right_gripper`，也没有给出它相对 `panda_hand` 的固定变换或整手碰撞包络。prompt 已提醒整手净空，但未给该机器人自身的固定 frame 关系。

现有公开 `camera_meta.wrist_camera` 包含 `physical_parent=panda_hand`、相机 hand-local 位姿及 world 位姿，因此可按 `T_world_hand = T_world_camera × inverse(T_hand_camera)` 反算手坐标，再与公开 `TCPpose` 比较。15帧均重建出 hand→TCP 平移 `[0,0,0.1]m`；最大平移残差 1.21071934e-08m，最大姿态残差 7.35066373e-11rad。此数值只验证已有机器人/相机坐标关系，不代表真实标定或碰撞净空精度。

**姿态必须同时说明：** `panda_hand→right_gripper` 的 quaternion 为 `[0,0,0,1]`（wxyz），绕局部Z旋转180°；二者不是同向坐标系，只有局部Z轴一致。`physics_capture.py:86–105` 读取此固定变换并用安装的 Lula 两frame FK核查；`:230–232` 将实际手位姿与该变换合成为公开TCP对应的状态。静态来源为 `standard.yaml:120–131`。

最小建议是在公开接口/提示中增加固定机器人标定：

> TCPpose is the world pose of the right_gripper frame, not the panda_hand/palm origin. The fixed transform from panda_hand to right_gripper is translation [0,0,0.1] metres and quaternion [0,0,0,1] in wxyz order. This origin offset is not the complete hand/finger collision envelope. Evaluate whole-hand and held-vessel clearance from the supplied camera views; no obstacle pose, safe height, or collision-free route is supplied.

若以JSON提供，应同时标明 parent/child、变换方向及单位，例如 `parent_frame=panda_hand`、`tcp_frame=right_gripper`、`parent_from_tcp={translation_m:[0,0,.1],quaternion_wxyz:[0,0,0,1]}`。不添加目标座世界坐标、障碍位置、路径、高度oracle、teacher阶段或实时器皿真值。

这个说明属于机器人本体固定几何，理论上已可从公开相机标定反算；直接表达能减少对隐含frame约定的依赖。它**不能**代替手掌/手指的真实包络或完整扫掠净空检查，也不能说明碰撞一定会消失。现有camera_meta的位姿quat未直写“camera-to-parent USD axes”；审计按匹配的local/world方向重建，若日后公开frame变换应清楚命名。

本次仅CPU读取已关闭公开观测与固定源码；未修改runtime、配置或prompt，未调用API/GPU，未读H5/物理raw/器皿真值。
