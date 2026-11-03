# LabSim Progress v1 工程验证报告

Progress v1 已实现器皿装载任务的在线逐步诊断和已有轨迹离线分析。九阶段由实际位姿、手指状态、接触、目标承托及稳定窗口计算；当前状态、历史里程碑与每次抓持尝试分开保存。原独立评分、reward、物理参数和数据资格保持原机制。

## 交付与使用入口

从 [Progress 使用指南](README.md)开始；坐标和字段见[映射表](field_mapping.md)，阶段和窗口见[判据表](stage_criteria.md)，结构见 [schema](schema.json)。主 README 的文档导航已加入中英文入口。

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration --progress \
  --output outputs/lab_cuvette_loading/Progress_v1/teacher_NEW

./labsim progress episode /absolute/path/to/closed/episode_0000 \
  --output outputs/lab_cuvette_loading/Progress_v1/offline_NEW
./labsim progress compare /absolute/path/to/online/episode_0000 \
  outputs/lab_cuvette_loading/Progress_v1/offline_NEW \
  --output outputs/lab_cuvette_loading/Progress_v1/comparison_NEW.json
```

正常 `collect`、`eval`、`serve` 也接受 `--progress`。单集、索引批处理、报告及精确比较共用项目 CLI；不需要特殊成功脚本。输出目录使用新路径。

## 实际验证

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 全部 CI 文件的本地 CPU 回归 | 1042 passed，1 skipped；67 项 Progress 测试 | cpu_summary.json、cpu_contracts.xml |
| 既有完整 Teacher 离线分析 | Progress 完成，30161 个物理采样，7539 个 transition，172 事件 | historical_replay.json |
| 既有 π0.5 未完成记录 | safety_stop；下一要求为 GRASP_NOT_ESTABLISHED；不伪造插入失败 | historical_replay.json |
| 原策略索引批处理 | 纳入 1 条 policy_evaluation；排除 10 条 resource_probe | actual_index_analysis.json |
| 真实历史轨迹经在线适配器回放与离线比较 | 7539 个 transition 的前后快照、事件、尝试及里程碑精确一致 | cpu_online_replay/comparison.json |
| 发布分支 CI | 运行代码与终局诊断修复均已通过远端 CI | runtime_ci.json |

CPU 跳过项是另一场景的一项 USD 测试：普通 CPU 解释器未载入 pxr。该项保留跳过标记；器皿任务的真实 Isaac 回归单独核查。

本轮正常 GUI Teacher 已完成一次连续完整装载；运行提交为 `913af8a5989dd328d22752a4bba6431339094306`。进程完整退出，退出码 0，整次墙钟 1265.07 s；原独立判分 `task_success=true`、`record_valid=true`、`success_bc_eligible=true`，Progress 完成且输出无错误。

记录包含 125.6667 s 仿真、30160 个物理步（含第 0 步共 30161 个采样）、7539 个控制 transition 和 172 个 Progress 事件。在线和离线逐 transition 前后快照、区间事件、reset、里程碑及尝试 **精确一致**，配置及物理采样数相同，差异列表为空。元信息和运行耗时分别保留，不要求序列化文件字节相同。

正式 ACT 和 DP reader 均读出实际 batch：动作 shape 为 `[3,16,8]`，图像观测分别为 `[3,3,256,256]` 与 `[3,3,3,256,256]`，全部有限。动作与后继状态相邻对齐，控制间隔为 1/60 s；双相机记录的时钟减去 engine 原点后，与观测时刻的最大标量残差约 6.56 μs。这是记录时钟核查，不是像素与物体位姿同步精度声明。

源 H5 为 1944763917 字节，SHA256 `9d5aafc90e265efc39500be2dbee653bbd2312bd6c959d15838fb52c088cdc50`；全部独立 H5 数据集已读取，三段原录像完整解码，物理／接触 gzip CRC 与 JSON 行读取通过。数据读取与分析前后源哈希不变。

| Progress 历史里程碑 | 首次确认时间 s |
|---|---|
| 接近抓取区域 | 12.2375 |
| 抓持 | 18.1417 |
| 完全离架 | 20.8500 |
| 到达固定预插入区 | 71.8333 |
| 对准 | 71.8333 |
| 有效插入到位 | 107.6083 |
| 目标承托 | 110.0542 |
| 实际脱指 | 112.1875 |
| 整手撤离 | 116.4167 |
| 连续稳定确认 | 123.4542 |

详细证据为 `online_teacher_closed.json`、`online_offline_consistency.json`、`official_reader_success.json` 和 `transition_clock.json`。原最终判分、完成标记、用途及启动指纹一起归档。


## 诊断语义与原判分对照

当前物理状态允许回退，历史里程碑保持。重试开始后，“下一项未完成要求”使用当前尝试，避免上次已搬运的历史事实让新尝试跳过离架。合法目标承托后的松爪不会成为抓持丢失；释放与撤离分别确认。服务超时归入服务中断，任务时间上限归入任务超时。

原记录的 held_transport_observed 表示持物横移，不表示到达预插入区。在历史成功样例中，两者分别为 44.3125 s 和 71.8333 s。Progress 的 0.1 s 抓持和 0.05 s 脱指时间比较含 1e-9 s 数值容差，原 scorer 的浮点直接比较可能晚一个物理步。详细实际输入、时间与条件见 historical_scorer_comparison.json；两套原始结果均保留。

稳定窗口采用因果持续计时。条件中断会重新开始，3 秒满足后才确认完成，不把未来确认提前标到候选起点。终局关闭尝试事件单独持久化，不回写过去的控制区间。

## 输出与运行代价

每集保存控制频率的 before/after 指标与稀疏事件，不重复保存图像或完整场景。复位第 0 步、第一控制观测、区间事件 `(t_obs,t_next]`、部分执行及终局事件分别归属。sidecar 完成关闭后才进入本轮发布；旁路失败记录 partial/interrupted，保留原任务结果。

本轮在线新增 Progress 文件共 15219003 字节。核心计算计时 36.89 s，物理注释与控制序列化计时合计 52.28 s；同轨迹离线注释约 19.77 s，离线生命周期约 48.15 s。在线分段计时不包含钩子外层深拷贝、输入哈希或报告生成，也不是开关配对的净增量性能测量。页面约 0.91 MB，只保留绘图标量、极值和关键边界；完整逐步值仍在约 15 MB 的 gzip 中。

H264 显示副本来自原始连续仿真视频，未合成、拼接或改变帧数与时长。原 MP4v 在部分浏览器不解码，阅读包使用 480×360 H264 副本；原视频、SHA 和完整 H5 保留在工程端。

## 几何与工程保护

固定任务仍为 cuvette_xy_1000，10×10×67.5 mm 尺寸假设、20 g 工程质量，完整 6×6 架 A1 和原内部 A 座。原座到任务装载轴的局部偏移为 `[0.00065,0.000001,0] m`，目标深度读取配置 0.027 m。物理 240 Hz、控制 60 Hz；场景随机化关闭。

从 PR 合入基线 f6dd2b2 开始实现；原资产、场景配置、scorer、物理采集核心、控制核心和其他新增场景的保护检查通过。历史 H5、标签和付费调用预算哈希不变。HF revision 继续为 bb880f098180c291f6f65995f969d48047207067；没有新资产发布、训练或付费策略调用。

## 复现与移交

新物理回归运行提交为 913af8a5989dd328d22752a4bba6431339094306；后续服务超时修复只修改终局域归类，不改变 update、物理采样或控制。最终发布提交、远端核对与对应 CI 由阅读包根目录的文件清单和 publication.json 记录。

完整原始数据位于工程 `outputs/lab_cuvette_loading/Progress_v1/`；报告 case 与 validation 记录具体 episode 身份及源 SHA。便携阅读包包含本轮成功、真实未完成例子、完整逐步 Progress、稀疏事件、参数、可视化和视频副本，不携带大型 H5、物理原日志、资产或环境。

## 使用边界与保留问题

只有 H5 控制端点时，标记 control_frequency_only；不能排除相邻端点之间的瞬变。输入材料采样与保守夹爪 AABB 净距按声明范围使用，实际 cooked 碰撞表面的全局误差仍未知。原生速度和位姿差分作为不同信号保留。上述范围不改变原任务资格。

首次新回归 teacher_online_01 在发布前中断，监护会话退出码 143，原生进程退出码未知；无完整关闭凭据，未作为合格数据分析。原始输出保留，使用独立监护进程重新执行 teacher_online_02；不推断内核或物理故障原因。
