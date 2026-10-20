# Env_v1 原始媒体与相机核查

本轮直接解码原始 MP4 的第0、36、48、96、132、142帧，重新查看四张照片。`reference_audit.json` 保存原媒体 SHA256、ffprobe 原始元数据、精确帧号、缩放及人工标点依据。143帧、3840×1080、2.4fps、59.584秒是影片编码信息，不是机器人控制频率或真实接触时序。

[双视角关键帧](reference_contact_sheet.jpg)、[四张照片](four_photos.jpg)、[初态关系标注](reference_layout_annotations.jpg) 显示：任务仪器位于左前景；完整白色6×6架在其右侧、开口一侧，机器人基座在右侧。视频中的另一台背景仪器按本轮要求省略。目标白色/透明器皿在近角、蓝色器皿在远角；精确槽号属于仿真配置。A座离盖板铰链较远，B座更近。盖板始终打开；没有关盖、测量和回收。机器人外观可见 neo 标识，但不能据此确认精确型号；当前 Franka 仍是代理。

图像无相机标定及量尺。标注的像素坐标是人工粗选的角色位置，不能换算出实测世界坐标。110mm来源架及仪器 CAD 的已有尺度不变；位置与朝向是根据关系与可达性提出的工程假设，须在新场景实跑核查。

[俯视提案](layout_proposal_top.png) 对应仪器原点 `[.36,0,.74]m`、yaw90°，架体 `[-.04,-.22,.74]m`、yaw−90°。这样从原座A到架中心约262mm，存在约70mm侧向偏移，不再用整机原点自动指向架中心决定yaw。完整机身 XY AABB 与架体 AABB 分离约32.3mm；这是 CPU 布局宽相检查，不是机械臂全路径碰撞验收。图中虚线是机身包围盒，不能当作实际实体或腔体。

## 相机实现

`demos/lab_cuvette_env_v1/cameras.py` 只建立两个持续传感器：

- `side_camera` 固定于世界 `/World/SideCamera`，从任务首个有效观测至末态保持外参不变。
- `wrist_camera` 真实挂载在 `/World/Franka/panda_hand/EnvV1WristCamera`，局部眼点 `[.055,0,.035]m`，目标 `[0,0,.12]m`，局部 up `[0,0,-1]`。在向下夹持的手坐标中，直立器皿长轴因此投向画面上方。

旧 demo04 的 `camera_2_rgb` 确实是 hand 子相机，并非第二个外部视角；但其 localup 取手局部+Y，造成器皿在画面中侧向。旧 wide/close 是另外的展示相机，不能代替本轮固定侧视。

原生图像640×480 HWC RGB uint8，策略图像经显式 INTER_AREA 拉伸到256×256 CHW，保存缩放后的内参，不隐式旋转或翻转。显示使用同一对物理相机，不能按阶段才启用腕视。新模块不推进物理时间；渲染与采样节拍由环境统一管理。

USD相机约定为−Z向前、+Y向上；OpenCV约定为+Z向前、+Y向下。四元数wxyz。每次 `get_meta` 输出实际local/world位姿、米单位外参、原生及策略内参、物理父link、帧号、传感器时间和读取仿真时间。重复帧号与黑帧分开标记，静止画面不等于传感器停更。

已检查本机 Isaac Sim5.1 的 `camera.py` 实现：focal_length和aperture API均按stage单位读写。配置cm/mm分别显式换算后下发，不再把旧数值的变量名当作物理单位。旧调用的FOV由比例决定，其命名不能证明真实焦距。新内参仍是合成设定，未经实机标定。

四项CPU相机轴/策略图像变换测试通过。本文及`reference_audit.json`不声称相机已完成Isaac渲染验收；新场景的实际黑帧、外参、可见性和全过程遮挡以根任务运行记录为准。

复现提帧与CPU证据：

```bash
PYTHONPATH=. /home/wujing/Desktop/vla/labutopia-env/bin/python docs/lab_cuvette_loading/Env_v1/reference/build_reference_audit.py
/home/wujing/Desktop/vla/labutopia-env/bin/python -m unittest tests.test_lab_cuvette_env_v1_camera_geometry -v
```
