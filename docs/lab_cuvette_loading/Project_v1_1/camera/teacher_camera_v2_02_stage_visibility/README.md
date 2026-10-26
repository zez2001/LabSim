# teacher_camera_v2_02：实际完整流程的阶段可见性

本次从干净提交`4d19b6ca836ca01c998abf4c4225946e09ffc80a`运行，已实际闭合并exit0。13个完整阶段快照（12个阶段边界加terminal）均已检查。它们来自同一次连续teacher流程，未拼接不同尝试。

**控制器走完流程，独立判分仍是失败。** 原始结果为`CONTROLLER_WORKFLOW_COMPLETE`，但`task_success=false, workflow_success=false, failure_type=GRASP_SLIP`；记录完整性和物理可信字段为true。实际观察到来源槽清出、释放、撤离，释放后3秒独立稳定窗口成立；grasp/transport/完整装载判定未通过，不能把末窗稳定或阶段齐全写成完整任务成功，也不能进入成功BC索引。

## 已看到的关键过程

- 来源端：腕相机可见完整网格、目标器皿杯口与上段、蓝色远角器皿和两指接近；初始架体靠近图像下缘，边缘余量小。闭爪后杯体下段被实际架壁挡住。
- 抬升/搬运：杯口、纵向轮廓、杯底与架体分离后的间隔清楚；side保留来源架、机器人、单台开盖仪器的全局关系。
- 腔口/预对准：TRANSPORT_HOLD及ALIGN腕图可以看见腔内两个方形金属座及开口，当前器皿对准的座在中央区域，手体上横梁没有挡住这些入口。
- INSERT：512low和640high均检查。杯体、口部、两指、中央目标座上沿与侧体可见；器皿自身逐渐挡住孔内空间，不能由单帧读取底部接触、全深度余量或微米偏差。
- SUPPORT_TRANSFER及OPEN入口：座的前壁/窗口、杯体与上沿关系可见，手指位于上方。side此时局部被手爪挡住，腕视补足。OPEN起点尚不能当作“已张开”。
- RETREAT入口112.9s：左右指已实际分开，器皿留在座内，指与杯体之间有清楚间隙。这是图像可见的脱指证据；承托力与稳定判定仍使用独立记录。

![来源与搬运](source_transport_views.png)

## 明确的剩余视野限制

VERIFY121.166667s与terminal124.266667s时，腕相机随机械臂撤离后朝来源架方向，目标器皿及座移到画面最左边，并被画幅裁掉一部分。side仍有全景，但目标器皿很小，手体投影也部分挡住它。640原生PNG及640high复核没有得到清楚的完整器皿稳定近景。

因此本次可以确认插入区域、支撑交接外观和实际双指分离的关键局部可见，**不能宣称撤离后整杯始终清楚可见**。对于后续纯视觉policy的最终状态复核，这是需要保留的观察盲区。当前没有修改挂点、相机、撤离动作或runtime来掩盖这个限制；该视野限制本身也不等于物理任务失败。

![装载、脱指与末视野](loading_release_verify_views.png)

## 文件与证据范围

`images/stage_XXXXXX/`复制每个阶段的两张未改动原JPEG和对应公开JSON；SHA与原数据一致。原图为512×384、q60、detail=low，无GT裁剪、检测框或高亮。512/640两套源编码及原生PNG仍保存在原输出，未改写。拼图仅用于阅读，不能当作模型原始输入。

全部teacher编码快照为`teacher_encoded_preview, api_sent=false`。本审计没有API/GPU调用，未读取H5、未压缩或修改活动日志。外部API比较由root另行执行，其结果须单独引用，不能把本页预览称作模型已收到的请求。

`visibility_summary.json`/`qa_progress.json`为已关闭的最终记录；`stage_visibility.csv`包含全部13帧的阶段、物理时刻、观测ID、公开夹爪开口/接触和逐视角评价。阶段名只在阅读sidecar和图表标签中，原公开输入不包含teacher阶段或物体真值。`original_result.json`、`original_independent_score.json`、`original_process_exit.json`及`original_run_manifest.json`原样保留标签；`manifest.json`记录来源和本目录SHA。

这些边界快照不是每个物理步的画面，不能替代连续录像、几何路径、接触力或独立判分，更不代表真实标定。
