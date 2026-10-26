# 公开机器人静态标定与 prompt v4

本改动仅更新 Project_v1_1 的 loading 任务语言和新 backend 提示，不改变旧 Project_v1 行为、执行器或物理参数。

`get_task_language()` 在原名义27mm装载目标之后追加机器人自身的固定frame标定。数值读取 `cfg.robot.tcp_local_m`、`tcp_quaternion_wxyz`，frame名读取 `tcp_frame`；当前为 `panda_hand → right_gripper` 平移 `[0,0,0.1]m`、wxyz `[0,0,0,1]`。文本明确它表示从TCP坐标到parent手坐标的变换，而非相同原点/相同朝向；100mm原点间距不是整手或手指的碰撞包络。

加载配置必须提供有限translation3、quaternion4及非空frame名，四元数范数与1的差不得超过1e-6；不静默归一化。无效标定抛出明确ValueError。非loading任务在读取任何新机器人/几何字段前即返回原父类语言，内容保持原样。

prompt v4只增加如何使用上述公共机器人标定，以及不能判断仪器边缘或整手净空时，应先取得双视图和视觉支持的净空，再水平搬运；不确定时观察或停止。保留此前透视对准、近座≤1mm/s、卡滞/相对滑动停止、足够装载深度与支撑交接后才松爪的规则。

公开字段仍为原 `task_language`，未增加物体真值、环境/目标座坐标、安全高度、专家轨迹或任务宏。五个通用工具、动作限制、模型、图像配置和context4保持原值。新增静态标定说明不能代替整手扫掠碰撞检查，也不能据此宣称后续GPT将成功。

CPU测试 **66通过**：配置变化反映到文本、实际语言方法只读取cfg（debug/robot/live-state属性毒化）、非法/非单位四元数拒绝、非loading旧行为、prompt边界、五工具与现有回执/预算回归。实际命令和源SHA见 `cpu_validation.json`。测试使用模拟HTTP回应，未调用API/GPU；本改动尚未重新做实际模型或物理验证。历史GPT03观测/原prompt与判分不改写。
