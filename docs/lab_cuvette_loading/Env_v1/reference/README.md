# Env_v1 原始媒体与相机核查

本轮直接解码原始 MP4 的第0、36、48、96、132、142帧，重新查看四张照片。`reference_audit.json` 保存原媒体 SHA256、ffprobe 原始元数据、精确帧号、缩放及人工标点依据。143帧、3840×1080、2.4fps、59.584秒是影片编码信息，不是机器人控制频率或真实接触时序。

[双视角关键帧](reference_contact_sheet.jpg)、[四张照片](four_photos.jpg)、[初态关系标注](reference_layout_annotations.jpg) 显示：任务仪器位于左前景；完整白色6×6架在其右侧、开口一侧，机器人基座在右侧。视频中的另一台背景仪器按本轮要求省略。目标白色/透明器皿在近角、蓝色器皿在远角；精确槽号属于仿真配置。A座离盖板铰链较远，B座更近。盖板始终打开；没有关盖、测量和回收。机器人外观可见 neo 标识，但不能据此确认精确型号；当前 Franka 仍是代理。

图像无相机标定及量尺。标注的像素坐标是人工粗选的角色位置，不能换算出实测世界坐标。110mm来源架及仪器 CAD 的已有尺度不变；位置与朝向是根据关系与可达性提出的工程假设。当前已有新场景预览、静止抓持与微抬失败的实际运行，尚未完成完整装载路径验收。

[俯视提案](layout_proposal_top.png) 对应仪器原点 `[.36,0,.74]m`、yaw90°，架体 `[-.04,-.22,.74]m`、yaw−90°。这样从原座A到架中心约262mm，存在约70mm侧向偏移，不再用整机原点自动指向架中心决定yaw。完整机身 XY AABB 与架体 AABB 分离约32.3mm；这是 CPU 布局宽相检查，不是机械臂全路径碰撞验收。图中虚线是机身包围盒，不能当作实际实体或腔体。

## 相机实现

当前实现以 `demos/lab_cuvette_env_v1/cameras.py`、`config/lab_cuvette_loading/Env_v1/native.yaml` 及实际extract01记录为准，建立两个持续传感器：

- `side_camera` 固定于世界 `/World/SideCamera`，从任务首个有效观测至末态保持外参不变。
- `wrist_camera` 真实挂载在 `/World/Franka/panda_hand/WristCameraV1`，当前局部眼点 `[.075,0,0]m`、目标 `[0,0,.35]m`、up `[0,0,-1]`。该配置已实际渲染，腕图可见完整架体；不能由可见架体推断所有阶段均无遮挡。旧 `/EnvV1WristCamera`、眼点 `[.10,0,.07]m`/目标 `[0,0,.14]m` 及更早 `[.055,0,.035]m` 只保留为历史候选，已不代表当前配置。

旧 demo04 的 `camera_2_rgb` 确实是 hand 子相机，并非第二个外部视角；但其 localup 取手局部+Y，造成器皿在画面中侧向。旧 wide/close 是另外的展示相机，不能代替本轮固定侧视。

原生图像640×480 HWC RGB uint8，策略图像经显式 INTER_AREA 拉伸到256×256 CHW，保存缩放后的内参，不隐式旋转或翻转。显示使用同一对物理相机，不能按阶段才启用腕视。新模块不推进物理时间；渲染与采样节拍由环境统一管理。

USD相机约定为−Z向前、+Y向上；OpenCV约定为+Z向前、+Y向下。四元数wxyz。每次 `get_meta` 输出实际local/world位姿、米单位外参、原生及策略内参、物理父link、帧号、传感器时间和读取仿真时间。重复帧号与黑帧分开标记，静止画面不等于传感器停更。

实际检查进一步发现：旧的很小USD镜头数值虽保持焦距/口径比例，renderer仍曾使用默认50/20.955投影，不能据USD属性或读取K宣称实际投影正确。当前在创建传感器前写入原生USD常用范围的完整镜头属性，并按本机5.1 setter乘10的数值约定同步。preview06实测P00分别为side=0.90670484、wrist=1.14531143，和声明K一致；见[投影修复对照](../data/preview06_projection_fix_comparison.json)。当前参数仅定义合成FOV，不代表真实光学校准。

修复前extract01[初帧fence实证](../data/extract01_initial_camera_flush_check.json)仅证明首帧一致；其[动态审计](../data/extract01_renderer_USD_dynamic_audit.json)观察到0.966282 mm最大残差和944个后续观测匹配上一control的状态，作为历史证据保留。随后fixed01采用官方zero_delay设置的[实际逐帧检查](../data/extract_fixed01_inspection/renderer_USD_sync_audit.json)中，935/935腕相机观测均匹配当前USD到1e−8 m，最大位置误差6.67e−16 m、旋转误差约5e−15°；已测软件渲染状态关联修复通过。它不是物理精度或真实光学校准，也不能仅凭矩阵确定实物曝光时序。手和前臂仍部分遮挡来源架，遮挡百分比未知。

[已安装源码核查](../data/installed_render_sync_source_audit.json)保留普通render、set_block_on_render及官方zero_delay设置的准确行段和SHA；普通render两次不能据此当作当前状态屏障。fixed01实际GUI窗口与两个官方设置已核查，且[物理前缀对照](../data/extract_fixed01_control_comparison.json)分别保留状态/命令精确一致及指力浮点差。record_valid只表示声明的记录完整性，不等同真实光学校准。

原CPU相机轴/策略图像测试和`reference_audit.json`是独立证据，不能替代上述实际渲染检查。官方depth大数组和完整renderer诊断只用于本地审计；策略使用明确RGB传感器白名单，修复前曾泄漏这些统计的Astra02不计观测边界合格样例。

复现提帧与CPU证据：

```bash
PYTHONPATH=. /home/wujing/Desktop/vla/labutopia-env/bin/python docs/lab_cuvette_loading/Env_v1/reference/build_reference_audit.py
/home/wujing/Desktop/vla/labutopia-env/bin/python -m unittest tests.test_lab_cuvette_env_v1_camera_geometry -v
```
