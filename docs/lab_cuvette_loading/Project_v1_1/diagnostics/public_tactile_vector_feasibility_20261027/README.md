# 原生指端向量公开的只读可行性审查

技术上可以把现有接触测量作为**明确声明、版本化的仿真触觉通道**提供；计算两个法向/摩擦三维向量不需要读取器皿当前位姿、座位姿、深度或独立判分。但现有通道静态筛选了指定任务器皿，不能称为不分物体的真实指端传感器，也不能静默加入当前 P6 或历史观测。是否实施等待 P6 实际结果与明确决定；本次没有实现或新实验。

## 已有通道与语义过滤

`PhysicsRecorder.capture` 从 `cup_fingers` 的 pair-force matrix 取 fm、从 friction patch API 聚合 ff；公开 `finger_contact_N` 已是每指 `norm(fm)`。`cup_fingers` 的 sensor 是 `/World/Cuvette`，两个 filter 是左/右指。因此当前标量本身已经带有“指定任务器皿与这两指接触”的关联，不是指端对任意物体的总接触。

把同一 fm/ff 的分量公开，不会新增动态位姿真值筛选，也不需根据目标座或成功状态选择数据；但会增加观测信息维度。静态器皿身份过滤必须写进传感器合同，例如“task-object-filtered simulated contact forces”。这里的“无器皿真值”应精确限定为无器皿位姿/深度/支撑标签，而非声称没有物体身份关联。不得再按 seat、接触位置、最近器皿、教师阶段或事后 slip/支持状态筛选或变换测量。

若要模拟通常的指端力传感器，应另设计以左右指为 sensor、聚合其所有接触的通道；那会把机身、座、架等接触也包括进来，是另一种传感器，不能与当前杯筛选数值混用。本审查不建议现在切换实现。

## 单位、坐标与时点的证据边界

已核当次记录器对法向/摩擦 API 均传实际 dt=1/240 s，场景为 SI 米制；API 用该 dt 将冲量转换为 **N**。cup sensor 与左右 filter 顺序已核。当前记录按 API 世界 XYZ 原样存储，安装 API 的 net-force 说明为世界坐标；没有额外读取杯旋转来构造向量。若以后要转为指端局部坐标，只能使用公开机器人 FK/固定标定，并显式声明旋转与受力侧。

on-cup 是现有 sensor 归属及 API 合同下的受力侧；没有完成独立正反作用力、坐标旋转或硬件标定实验。摩擦 API 是逐 patch 的切向向量聚合，不是已校准六轴力传感器，也没有证明所有求解器接触均被覆盖。不能把未知力直接补零；应分别声明 normal/friction 的 available、单位、frame、force_on、采样时间和物理步号。

采样来自已完成物理步后的同一 debug snapshot；公开观察通常为控制边界的最新样本。重复 observe 不推进物理，也不产生新的力样本；相机与状态时钟仍各自保留。不得暗加 240 Hz 历史、子步峰值、滑移判定或自动 stop。新增向量本身不会缩短仍在执行中的长动作。

## 同一环境可得与所有模型实际使用须分开

应先由 Project_v1_1 task/facade 统一输出版本化测量，让 GPT、RPC 和其他后端看到同一份 episode/observation/time 绑定、同单位同顺序的数据；不得给 GPT 单独读取 recorder 私有字典。现状并不等于所有后端已有相同触觉输入：GPT `PUBLIC_FIELDS` 保留标量，而历史 RPent/Harness 的 `policy_observation` 白名单连该标量也会移除；π0.5 LIBERO encoder 固定使用八维机器人状态，不含触觉。

因此共同 API 可提供相同可用通道，但既有模型未必支持或消费它。后端应显式报告 supported/ignored/unsupported sensing，不能悄悄往原八维状态拼向量。若训练/BC 要使用新触觉，需新版本可选公开数据字段和明确 reader/model 配置；保持原 agent_pose/actions 语义，不修改历史 H5、旧 reader 或旧实际模型输入。

## 最小涉及位置与后续验收

- 新 task `tasks/lab_cuvette_loading_project_v1_1.py`：版本化公开 getter；避免修改旧 V1 getter。原 recorder 已有 fm/ff，通常无需为公开而改物理采集。
- 新标准配置/观测契约：声明传感器来源、杯身份过滤、frame、受力侧、shape `[2,3]`、单位、availability 与采样时点。新观测导致新的配置/源码 fingerprint，不能删依赖以伪装与旧观测相同。
- GPT `cubence_tools.py` 的公开投影及 `cubence_project_v1_1_visual_context.py` 的当前/历史白名单、说明与实发保存；只改 prompt 不会传入新向量。共享路径必须保留旧版本默认行为。
- RPC 现有 ndarray 编码能承载二维数组，但新观测版本元数据与 RPent/Harness 投影需显式接通；π0.5 固定 encoder 不应自动扩维。
- 如需正常数据训练支持，再扩新 collector/dataset 的可选公开测量记录及 feature 配置；旧 8D 状态与历史文件保持。
- 后续至少验证字段白名单隔离、finite/available/shape、同 snapshot 时间/ID、RPC/GPT/历史包原字节可追溯、旧版输出不变，以及实际 native 新运行中的单位/受力侧。此处未执行这些未来验收。

原 [GPT04 指端早期信号审计](../gpt_debug_04_finger_observability/README.md) 只证明该次轨迹中未公开摩擦变化较强、公开法向再分配有线索；不证明向量能唯一识别滑移、底部支撑或安全间隙，更不保证后续策略或其他模型成功。当前评分、物理、力上限、控制 helper 和所有旧标签不应因“公开测量”自动变化。

本次只读源码与既有闭合证据，未读活动教师 5、未新增 GPU/API/公共字段或测试轮次。实际所读源码 SHA256 和审查快照见 [review.json](review.json)。
