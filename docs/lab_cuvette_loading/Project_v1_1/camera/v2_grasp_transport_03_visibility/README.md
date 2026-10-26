# 腕相机 v2：实际闭爪与抬升快照可见性

已只读检查实际闭合的grasp_transport_03（v2）与此前grasp_transport_02（v1）三个阶段的完整512×384、JPEG q60、detail=low编码预览。每张复制文件与原预览SHA256一致，没有GT裁剪、检测框或模型输入标注，也没有发送API。

![完整帧阶段对照](whole_frame_wrist_comparison.png)

实际metadata确认：旧eye约[0.075,0,0]，新eye约[0.075,0,0.04]；目标方向也对应此前CPU候选。v2在closed和extracted时，手体横梁遮住的连续上方带明显减少，杯口、夹指之间杯体和更长的纵向轮廓更清楚。人工粗观察该上方带由约160px减至约60px（帧高384px），这不是分割面积或全图遮挡率测量。

closed阶段的杯体下段仍被来源架壁遮挡；双指仍遮挡部分侧壁。extracted/short_transport快照可见更多杯体、来源架格和远角蓝色器皿。由图像可以观察相对关系，不能仅凭单帧确认物理保持、无滑移或承托。

两轮原始诊断均记录grasp_success=true、source_slot_cleared=true，但没有插入、释放或撤离；终止仍为CONTROL_DIAGNOSTIC_COMPLETE/POLICY_BUDGET，不是完整任务成功。teacher_camera_v2_01则在接近阶段就速度停止，不能补齐后续关键阶段。

这是一组阶段可见性对照，**不是纯粹只改相机的像素A/B**：03还启用robot-state跟踪补偿，阶段时刻、实际手爪与器皿姿态略不同。完整腔口进入、座内插入、支撑、开爪和撤离可见性须待新teacher完整流程实际检查；当前不能宣称新挂点已验证全过程清晰。

原始公有状态、编码变换、阶段时间、安装姿态和图片SHA在visibility.json与manifest.json；已复制6张未修改原JPEG。拼图是阅读用展示，不是实际模型输入文件。本分析无GPU/API、未读取H5、未修改runtime或原始输出。
