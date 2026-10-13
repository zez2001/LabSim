# LabSim 器皿装载 V0 实验报告

代码分支 codex/lab-cuvette-loading；物理控制/判分实现独立于 minimal_pick 和 minimal_precision_insertion。数据目录：/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading。

## 已运行结果

- standard10_verified_V0: 10/10 完整成功；分类 {'SUCCESS': 10}；模拟时间合计 208.96s；episode 墙钟合计 421.26s（不含子进程启动/汇总）；最大静态几何重叠 0.010495mm。
- appearance_check_V0: 1/1 完整成功；分类 {'SUCCESS': 1}；模拟时间合计 20.90s；episode 墙钟合计 42.25s（不含子进程启动/汇总）；最大静态几何重叠 0.010495mm。
- layout_check_V0: 1/1 完整成功；分类 {'SUCCESS': 1}；模拟时间合计 20.90s；episode 墙钟合计 43.98s（不含子进程启动/汇总）；最大静态几何重叠 0.004576mm。
- random_test_V0: 20/20 完整成功；分类 {'SUCCESS': 20}；模拟时间合计 418.04s；episode 墙钟合计 878.49s（不含子进程启动/汇总）；最大静态几何重叠 0.015996mm。
- collection_V0: 20/20 完整成功；分类 {'SUCCESS': 20}；模拟时间合计 418.03s；episode 墙钟合计 865.33s（不含子进程启动/汇总）；最大静态几何重叠 0.008815mm。
- standard_replay_V0: 1/1 完整成功；分类 {'SUCCESS': 1}；模拟时间合计 20.90s；episode 墙钟合计 41.51s（不含子进程启动/汇总）；最大静态几何重叠 0.005050mm。
- random_replay_V0: 1/1 完整成功；分类 {'SUCCESS': 1}；模拟时间合计 20.90s；episode 墙钟合计 43.96s（不含子进程启动/汇总）；最大静态几何重叠 0.004926mm。

## 证据与判分

从来源架中的动态透明方形器皿开始，实际双指接触夹取、提取、搬运、进入仪器内装载座、张开撤离并独立稳定至少1秒。控制只下发机器人关节目标；没有运行中设置器皿位姿、运动学器皿或夹爪绑定。成功要求实际装载深度≥18mm、朝向误差≤5°、释放/撤离、稳定漂移≤0.3mm及全程静态实体重叠≤0.25mm。标准/随机条件使用相同判据。最大深度限定于目标邻域；脚本阶段不能代替实际成功。

USD 新进程独立加载、两次复位、原生 Cube 尺寸和空目标孔的 PhysX 底面射线检查保存于 usd_reload_check.json。穿透检查对器皿五个壁/底与静态碰撞 Box 做实际姿态的15轴 SAT；没有声称读取全部 cooked shape，也未完整覆盖机器人网格/动态干扰器皿的全部重叠。

全量数据审计：已生成，详情见 /home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/all_audit_V0.json。实际9维关节状态，8维对称夹爪动作；RGB CHW uint8、256×256、60Hz控制周期采集。obs/action/next_state、终止标记、有限状态、RGB和episode边界均由审计检查；ACT/DP只读取batch，没有训练或策略成功证据。

物理回放使用该条轨迹的实际初态和采样布局，执行记录的机器人绝对关节动作，不回放器皿位姿。显式位姿/速度恢复不包含隐藏的PhysX求解缓存；回放是否成功以上面的独立结果为准。

## 场景重现与限制

逐段查看143帧/2.4fps/59.584s双视角视频及实际提供的4张照片，提取13个关键时刻。复现白色来源架、蓝色工作区、开盖白色仪器/黑色腔、腔内座、近邻结构、绿幕和双视角。未确认真实“neo”机器人型号，采用既有Franka代理；面板、背景和邻近已装器皿作简化。器皿13×13×45mm、20g、装载内宽15mm/深20mm均为合成原型值；图像只提供关系参考，不提供尺寸标定。

采用PhysX CPU/TGS，240Hz物理/60Hz控制、4子步，有限87/12N·m手臂力矩和8N夹爪力；SI运行时增益/速度/力上限已读回。contact/rest offset为0.1/0mm，摩擦/求解配置固定；没有混入物理参数随机化或重做亚毫米扫描。接触冲量按当前physics_dt换算力。

随机范围：架体XY±10mm/yaw±3°，仪器XY±5mm/yaw±2°，合法前排槽位及槽内±0.25mm、光照0.8–1.2及材质色。A外观、B布局独立检查；测试2000–2019与采集3000–3019预先冻结且分开。初始化几何/稳定性不合法记录失败，不按专家成败替换seed。本轮不拓展后排密集抓取。

固定标准重复只能说明当前canonical初态的运行重复性。随机20条件与20采集尝试只能说明声明范围下的原型结果，不是广泛真实场景成功概率。全部成功也不构成真实仪器/真实机器人精度或real-to-sim gap结论。

## 工程问题与后续真实数据

同一Isaac进程多次换空Stage出现旧相机渲染节点错误，改用每episode新进程并顺序汇总；批次路径硬链接兼容性问题也已修复。开发/基础设施调试输出全部保留，清单development_attempt_inventory.json；其成功/未完成记录不混入正式验收批次，也不作学习数据。没有隐去物理失败或放宽阈值。

当前没有真实校准数据。导入接口区分静态关节状态画面检查和命令响应仿真，检查单位/坐标/关节名/动作语义，拒绝跨机器人绝对关节回放。接口合成夹具只验证功能；参数导入创建新V1及历史，不覆盖V0，最终验证数据禁止调参。后续先确定真实机器人/工具，再测尺寸/质量/布局/相机并替换估计参数；重新验收standard/random/判分/旧回放后，以独立真实验证数据判断模型差距。

自定义LabSim任务借鉴RoboDojo配置/seed/汇总理念；不属于RoboDojo官方评测。不操作真机，不模拟光谱/液体/化学结果，不开展ACT、Diffusion或VLA训练。

## 交付索引

- 运行命令：[README](/home/wujing/Desktop/vla/LabSim/demos/lab_cuvette_loading/README.md)。
- 规格/来源/假设：[task_spec](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/task_spec.md)，参数来源清单位于config/lab_cuvette_loading。
- 真实接口：[real_data_interface](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/real_data_interface.md)。
- 全部episode记录：[CSV](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/results_V0/episodes.csv)；代表视频索引：[JSON](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/results_V0/representative_videos.json)。
- 唯一inode输出体积 38.980 GiB（含保留调试输出和成功合并HDF5；硬链接不重复计）。显存为各episode结束时nvidia-smi整卡样本，包含其他桌面进程，非严格峰值或独占性能测量。

![场景关系对照](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/results_V0/scene_comparison.png)
![实际采样布局](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/results_V0/random_actual_layouts.png)
![目标深度与几何重叠](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/results_V0/depth_overlap.png)

## 补充验证（2026-10-14）

- 保留验证 seed 4000、4001，各一条完整任务均成功；与测试/采集 seed 分开。
- 主入口 main.py 的 GUI 模式实际跑通一次；记录目录 20261014_000722。
- random seed 2000 另一次新进程采样/物理初始化，与原始初态的物体位置和9维关节最大差均为0（计算状态复位检查，不代表真实定位精度）。
- 物理回放的共同动作完全一致；标准/随机物体路径最大位置差分别0.454337/0.336756mm，RMS分别0.177843/0.146109mm，两条仍由独立判分成功，未以物体位姿重放消除差异。
- 真实导入接口仅使用合成夹具；静态画面模式、动态命令响应模式、单位转换和新版本参数历史已检查。动态响应比较明确使用 action_t 后的 state_(t+1)。最初的接口启动因未继承现有 EULA 环境变量失败，日志保留；修正环境后运行。早期响应时间标记版本保留供调试，正式接口证据采用 synthetic_command_response_aligned_V0。
- 本轮没有真实测量数据、校准、gap评估或学习策略训练/验收。

参考理念：[RoboDojo仓库](https://github.com/RoboDojo-Benchmark/RoboDojo)、[文档](https://robodojo-benchmark.com/doc/)。本任务在LabSim中独立实现，不报告官方评测成绩。
