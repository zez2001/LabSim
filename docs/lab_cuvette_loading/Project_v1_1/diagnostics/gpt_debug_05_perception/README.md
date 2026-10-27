# GPT05 实际公开输入与时序参考审计

原进程PID1211605已消失、exit0，实际runtime58da857e14a0a1152884e13984607a286547a046。原完整任务false SAFETY_COLLISION/ROBOT_ENVIRONMENT_COLLISION；record/integrity/physics true、BC false，来源槽清出true但原全程grasp/transport false。没有装载、释放或独立撤离，post_retreat_window=unavailable、stable_after_retreat=null。原标签不改；具体native碰撞pair交由独立闭合物理审计，本目录不读raw/H5。

25次真实请求逐ID join原共享ledger，全部HTTP200/statusOK且returned model字段gpt-6-astra，估算2.778234美元。当前25个公开JSON/50张当前exact JPEG和40张历史腕图字节副本已全部保留，233份原gpt_control文件全覆盖。P6/side v3/wrist v2/640×480 q60 high/context4确实生效；不是先前P5取消队列或观察QA。首次公开双侧>0.02N参考是D7/t14.016667，全部后续参考固定；previous是上一distinct ID；每次current最后、动作使用current ID，历史时间严格更早。无teacher阶段、物体/座真值坐标或自动任务宏。

[动作CSV](action_sequence.csv)保留25行，包括最终error：D24在48.016667秒请求world+X35mm/2秒，实际执行114/120tick、1.9秒、456物理步，在49.916667秒安全停止，target_reached=false。其[完整原error行](final_error_record.json)保留原model_tool_calls arguments字符串及native partial receipt，不能因普通decision表没有最后行就漏掉实际尝试。全部累计2994控制tick/11976动作物理步，另有初始化4物理步。24条整段、1条部分；不自动重放。

任务运动是来源架接近、D6闭爪、D7–14连续8次40mm抬升，再D15–24水平搬运。**闭爪后没有向仪器下降、100µm入口动作或近底微步**。因此只能说P6时序视觉输入实际使用，不能说入口100µm策略被验证、解决了接触滑移或完成任务。CSV中的analyst_public_motion_segment是离线按公开指令归类，不是模型收到的teacher阶段。

实际输入关键帧：[抬升后侧视D15](gpt_control/observations/decision_000015/side_camera.jpg)、[侧视D21](gpt_control/observations/decision_000021/side_camera.jpg)、[侧视D23](gpt_control/observations/decision_000023/side_camera.jpg)、[碰撞动作前侧视D24](gpt_control/observations/decision_000024/side_camera.jpg)和[同次腕视D24](gpt_control/observations/decision_000024/wrist_camera.jpg)。主审与[第二位独立视觉审查](independent_public_visibility_QA.json)均只看原全帧：竖直开盖在side明显可见，但掌腕投影遮挡其部分边沿；wrist能看杯/指垫/下方腔口，不能补齐整掌与后方盖板的三维正净空。故不是“障碍完全不可见”，也不能据图证明净空或具体碰撞prim；未保存模型私有推理，不能断言模型当时如何判断。

[汇总JSON](summary.json)核对每次public JSON/JPEG/manifest/动作ID与时长；[来源与复制清单](manifest.json)记录238个原nonraw SHA前后不变。时序manifest的公开投影hash与所有图像都可核验；6个决策没有private item，可重建同一完整input_items。其余含原provider reasoning等redaction，保存的是其类型/哈希而非内容，不能独立重建完整input_items或HTTPbody。usage里的reasoning token数量不代表保存了推理文本。完整实时工具响应组由原runner维持，图片/公开JSON的精确性不等于保存全部私有memory或请求头。

可离线运行 `python3 verify_public_inputs.py`，只用标准库验证当前目录复制SHA、各公开projection和图像、可重建input hash及最终partial回执，无网络。没有保留原数据集H5或raw，也不承诺JSON中原绝对路径为包内实体。传感器rendering和状态时间分别保留，不能据API暂停检查声称像素严格同刻。
