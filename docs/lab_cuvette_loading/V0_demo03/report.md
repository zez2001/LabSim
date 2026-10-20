# LabSim V0 demo03 视频场景装载报告

日期 2026年10月20日。项目 LabSim，独立版本 V0_demo03，模式 video_demo_adapted。

已在完整白色6×6来源架和开盖仪器腔内A适配座之间完成连续物理装载、支撑交接、实际松爪、撤离和3.1秒稳定观察。固定复测已完成5次，独立成功5次；小范围随机已完成10次，独立成功10次。另1次工具会话中断未评分，原记录保留。现有加载器实际读出主片同源的训练格式batch，未开展训练。

本次完成的是视频结构对应的仿真适配任务。完整白架由 Python 参数化创建；腔内 A 座在原安装位置重建了配合通道。原器皿与原座的尺寸冲突、厂家型号未知和真实动力学未标定等事实仍保留，native_pair_success 与 real_calibrated 均为 false。适配任务的数据资格由自身独立判分产生。

## 1 场景与原视频的对应

原视频中的完整白色6×6架、近角取物、远角蓝色器皿、两台仪器以及开盖后的内部装载位置均作为本轮结构关系依据。A1对应架局部−X、−Y近角，F6为对角蓝色邻物；字母沿局部+Y、数字沿+X增加。全部36槽保留可见空腔和真实壁体，蓝色邻物为独立动态器皿。

selected_target_seat_id 固定为 candidate_far_hinge，即距铰链较远的 A 座。用户已确认两座均可承担目标角色；厂家功能名未知不再阻塞选择。另一座 B 与其余仪器结构继续保留。盖板沿用demo02估计的近90°开盖姿态：原CAD主面为41.566965°，派生刚体再转48.433035°；不是实测铰链标定。本轮没有增加关盖、测量或回收动作。

![原任务与本轮完整白架场景的角色对应 工程槽位编号不代表实物标定](media/random8000_full_view/reference_scene_correspondence_vertical.png)

![原视频腔内A与本轮派生A座的对应 保留另一B座及原CAD配套结论](media/random8000_full_view/reference_internal_A_correspondence_vertical.png)

全景位置由可达性和碰撞检查确定，是视频场景的工程布置。没有相机标定与实物标尺，因此不声称精确恢复了视频中的绝对距离、色彩、外观或开盖铰链位置。

## 2 资产来源与局部适配

| 对象 | 实际来源与生成方法 | 本轮使用与修改 | 证据 |
|---|---|---|---|
| 器皿 | 提供的源网格，经ext01标准化；复用ext02 walls28_mm | 外形、14.85mm外宽、67.5mm高度和28块壁体碰撞保持不变 | asset_changes.json及源SHA |
| 完整白架 | 视频行列及外观；Python参数化 Cube | 新建50个实体分块和36个真实开口，全部底面及隔板碰撞 | rack.usda及build_assets.py |
| 仪器与盖板 | 原newnew4.usd，复用demo02单位及开盖变换 | 机身原尺寸不变；沿用demo02近90°派生开盖姿态 | instrument_demo.usda派生引用 |
| 腔内A座 | 用户确认目标角色；原安装坐标 | 以5个有厚度Cube重建16mm配合通道，外包络保持20.4×20.4×29mm | adapter_A.usda及替换路径 |
| 腔内B座及邻近结构 | 原CAD其余7个源网格 | 不改尺寸；保留视觉和碰撞 | manifest重载检查 |
| Franka与控制 | 项目Franka.usd及Lula IK | 复用关节位置控制、物理夹爪和原采集器 | robot配置及运行快照 |

定向核查ChemLab Ziath DP5的rack_24、48、96、240及geometry_manifest，实际布局分别为4×6、6×8、8×12、12×20，没有直接匹配的6×6。其管体为另一个合并OBJ，不能当作架体碰撞。最终没有导入ChemLab模型或代码；它只作为结构参考。固定版本、下载清单、哈希和许可见 [来源说明](source_and_assumptions.md) 与 [ChemLab核查](chemlab_reference.json)。

原A在派生层同时禁用视觉实例与对应SourceMesh3碰撞，再在同一instrument局部坐标添加新A。源CAD没有被修改；另一B和其余部件仍激活。重载后instrument碰撞数为7个保留网格加5个适配座实体，共12个。没有隐藏旧孔或残留旧A碰撞。

## 3 最终尺寸与物理设定

| 对象或量 | 当前值 | 来源或定义 | 真实校正需求 |
|---|---|---|---|
| 器皿外宽与高度 | 14.8500×14.8500×67.5000mm | 原实际顶点及累计变换 | 实物尺寸与公差 |
| 来源架 | 110×110×28mm，6×6 | 参数化工程设计 | 外形、行列比例与实测尺寸 |
| 来源槽 | 净宽16×16mm，深25mm；壁2mm，底3mm，孔距18mm | 用户建议的可配置假设 | 槽形、深度、壁厚 |
| 来源露出高度与抓取点 | 42.5mm；抓取点距底53mm | 原器皿高度及架深；夹指净空 | 实际抓取区与摩擦 |
| A适配座 | 外20.4×20.4×29mm，内16×16mm；壁2.2mm，底2mm | 保留原包络的工程重建 | 原生配合通道与承托结构 |
| A可用深度 | 27mm，器皿终态露出40.5mm | 座高减底厚；沿全深度检查 | 实际承托高度与插入方向 |
| 单侧名义余量 | 0.575mm | (16−14.85)/2 | 不能当作真实定位精度 |
| 机身主网格 | 520.5×630×230mm | 源网格完整变换 | CAD与实物一致性 |
| 原CAD开盖整体 | 520.5 × 634.625 × 435.481 mm | 原盖板姿态的8网格包络 | 原文件与实物关系 |
| 本轮派生开盖整体 | 520.5 × 630 × 577 mm | 近90°估计姿态的重载包络 | 实际铰链与开盖角 |
| 器皿质量 | 0.020kg | ext02工程假设，非实测 | 质量、质心、惯量 |

SI米单位，Z向上。以下为标准配置、随机扰动前坐标；主片seed8000实际装配平移另保存在config.yaml的randomization.actual。来源架world原点为[−0.04,−0.22,0.74]m，A1槽底[−0.085,−0.265,0.743]m。instrument原点[0.36,0.18,0.74]m，A局部原点[−0.1499155,0.1476294,0.145]m，承托面world为[0.2100845,0.3276294,0.887]m，座口Z=0.914m。槽和目标均由装配坐标计算，不依赖旧机外槽。

复用Isaac Sim 5.1.0.0、Python 3.11.16与RTX 4090。物理240Hz、控制60Hz，每动作保持4个物理步；CPU dynamics、MBP、TGS、位置/速度迭代64/1、CCD启用。USD写入的contact offset为50μm，rest offset为0；一般静/动摩擦0.6/0.5，指面1.0/0.8，恢复系数0。这些是沿用的工程参数，不是测量值，也不是精度保证。原生烹饪形状的完整表面与offset回读仍不可用，runtime.json明确记录native_offsets_readback为null；不能宣称已排除全部烹饪误差。质量分布及主惯量保留ext02按源材料积分的假设，详细值见 [尺寸表](dimensions.csv)。

视觉与碰撞几何分离。新架和适配座两侧使用同尺寸Cube，不把孔整体凸化；器皿复用28块材料壁体，仪器静态结构沿用三角网格。原生速度、USD属性速度和位姿差分全部保留，角速度单位分别按接口记录，冲量按当前physics_dt换算力。

## 4 几何检查与失败修复

先检查槽位合法初态、全深度通道及器皿外轮廓，随后核查手掌与双指。首次真实运行仍在搬运中发生link6碰盖板，说明只检查手部不能替代整臂检查。新增整臂Lula IK及FK计划诊断，覆盖11个有碰撞输入的刚体；用输入凸包包络和三角面检测对照保留的仪器源网格。

最终搬运器皿底部高度为0.975m，先沿Y到目标Y，再沿X进入仪器；松爪后先升手60mm，再向世界−X横撤120mm。最终计划没有观察到输入网格相交，实际运行同时检查原生接触。采样计划与输入几何不能证明全部PhysX烹饪表面误差已被排除。

| 尝试 | 实际终止阶段 | 观测证据 | 本轮修复 |
|---|---|---|---|
| dev_01 | 27.6167s TRANSPORT | link6与盖板实际接触 | 降低搬运高度并做整臂检查 |
| dev_02 | 48.6167s INSERT | 插入前实际XY约−0.674/−0.281mm，入口受力并相对TCP上滑14.22mm | 更新持物偏置，实际器皿XY反馈控制 |
| dev_03 | 61.75s VERIFY结束 | 完整流程及独立15项检查通过 | 冻结配置后复测 |

dev_02最终指面与座壁为零冲量、正间隔的接触skin候选，保守停止不能直接称为实体穿透；此前器皿与西壁的约5.97N实际受力则有记录。没有用控制命令推断已装入，也没有把该失败改标成功。详细诊断见 [接触与滑移分析](data_audit/dev02_contact_diagnosis/README.md)。

ALIGN使用实际器皿位置修正TCP目标，下降时继续有界的小幅XY修正。它不使用视觉，属于工程状态反馈控制；只下发机器人关节位置目标，器皿仍由物理夹持运动。不是对原CAD尺寸冲突的规避，原冲突仅通过明确的新A配合结构解决。

## 5 支撑交接和同一次连续成功

支撑力只统计A/Base的净竖直分量，双指法向与摩擦分开保存。接触时底座数N的瞬态主要由向下的指面摩擦抵消，不能将接触模长和当作重量。接触目标底面后停止继续下压；检测实际底部与目标座承托力，3秒内逐步卸载，必要时最多1mm轴向微抬目标以解除顶压。通过0.5秒位姿与支撑观察窗口后，双指缓慢对称张开，确认实际关节开度及接触力消失，再抬手横撤。原生速度与位姿差分不一致保留告警，不让该差异单独导致永久停在松爪前。

| 阶段 | 开始秒 | 实际行为 |
|---|---|---|
| RESET | 0.000 | 来源槽内自然落稳 |
| APPROACH_SOURCE | 4.000 | 接近指定A1 |
| GRASP | 11.000 | 双指物理夹持 |
| EXTRACT | 13.500 | 实际拔出抬升 |
| TRANSPORT | 20.500 | 避盖板搬运 |
| ALIGN | 29.500 | 实际器皿XY反馈对准 |
| INSERT | 32.000 | 下降进入腔内A |
| SUPPORT_TRANSFER | 47.233 | 停止顶压并逐步卸载 |
| OPEN | 50.733 | 双指慢开且确认脱离 |
| RETREAT | 53.183 | 抬手后横撤 |
| VERIFY | 58.683 | 撤离后3.1秒稳定检查 |


最终主片seed8000的撤离后窗口为58.683333至61.783333秒，共745条物理状态；目标底面竖直力最小约0.196164N，与20g假设重量一致。三手部输入包络与器皿实际位姿的分离距离保守下界约111.885mm。窗口源几何已观察到的最大穿入为0.000μm，低于原50μm门槛；位姿变化满足0.2mm及1°稳定门槛。末态XY偏差约[-0.45723,+0.00507]mm，实际深度26.9999mm，仍在适配通道内。该横向偏移是释放后的物理结果，不能写成精确居中；微小浮点变化受接口数值表示影响，不代表真实平台精度。

![主片同一次记录的支撑交接与实际松爪 竖虚线依次为交接 松爪 撤离](figures/main8000/support_open.png)

最终主录像从同一seed8000的来源初态录到撤离后稳定，1920×1080、30fps，没有拼接不同尝试。近景取同一原始轨迹，画面标注阶段、仿真时间及版本。视频容器编码时长可包含末帧，不替代状态时间戳。

## 6 独立判分和批次结果

独立判分读取实际物体位姿、几何检查、关节开度、接触与阶段记录，不直接复制控制器success。它检查来源槽合法支撑与清出、正确A通道及承托、双指真实脱离、实际撤离净空、连续至少3秒稳定、50μm源几何穿入门槛、有限原生信号、连续物理采样以及无运行中绑定或器皿运动学替代。所有15项均须成立，才写入独立适配任务的数据资格。scene_correspondence_accepted单独记录场景结构验收，workflow_success记录连续任务结果；native_pair_success和real_calibrated保持false，data_eligible仅表示本适配仿真范围可用。

未进入VERIFY的失败，其post_retreat_window为unavailable，stable_after_retreat为null；中止前末段单列terminal_window。历史seed7000仍为原50.289μm超过50μm门槛的失败，本轮没有提高门槛。

固定批次独立成功5/5、数据资格5/5；随机批次独立成功10/10、数据资格10/10。固定批处理外壳在任务全部完成后的汇总阶段返回143，原因未确证；五条H5与末状态已完整关闭保存，原空summary保留，新summary_recovered_01只读重算确认结果，不重跑或改标轨迹。随机按相同配置与seed逐条顺序启动，原进程退出码另记录。原seed8008的工具运行会话返回143，最后日志在INSERT，无末态评分，原因未知；原目录不动，单列为1条未完成中断，在random_recovery_20261020_01以相同seed新目录继续。最终共19次启动、18条完整结束、1条未评分中断；该中断不算成功或物理失败，也不进入正式10条的合格索引。

| 记录 | 槽位 | 独立结果 | 仿真秒 | 撤离后秒 |
|---|---|---|---|---|
| fixed_0 | A1 | SUCCESS | 61.750 | 3.10 |
| fixed_1 | A1 | SUCCESS | 61.750 | 3.10 |
| fixed_2 | A1 | SUCCESS | 61.750 | 3.10 |
| fixed_3 | A1 | SUCCESS | 61.750 | 3.10 |
| fixed_4 | A1 | SUCCESS | 61.750 | 3.10 |
| seed_8000 | A1 | SUCCESS | 61.783 | 3.10 |
| seed_8001 | A2 | SUCCESS | 61.817 | 3.12 |
| seed_8002 | B1 | SUCCESS | 61.883 | 3.10 |
| seed_8003 | B2 | SUCCESS | 61.833 | 3.10 |
| seed_8004 | C1 | SUCCESS | 61.783 | 3.10 |
| seed_8005 | A1 | SUCCESS | 61.783 | 3.10 |
| seed_8006 | A2 | SUCCESS | 61.817 | 3.12 |
| seed_8007 | B1 | SUCCESS | 61.783 | 3.10 |
| seed_8008 | B2 | SUCCESS | 61.817 | 3.12 |
| seed_8009 | C1 | SUCCESS | 61.767 | 3.10 |


wall_seconds沿用执行器的局部墙钟计时，不包括SimulationApp冷启动和其后大型JSON写出/关机，不能当作端到端性能比较。正式15条轨迹中，源几何采样已观察到的最大穿入为14.671μm，撤离后窗口最短3.100秒，三手部包络与器皿分离距离的保守下界最小111.847mm。它们是当前定义下的观测值，不是烹饪几何的全局误差界。固定初态重复仅用于重复性检查。随机检查限定为5个可达槽A1、A2、B1、B2、C1，以及架体和仪器装配各自XY±1mm平移；yaw与槽内横向扰动为0。每个槽出现两次。架体带槽位/蓝杯一起平移，仪器带A/B/盖板一起平移。该小样本不代表全部36槽、任意布局或真实任务成功概率。

![主片同一条轨迹的实际偏差与深度 灰虚线仅为名义单侧余量不是成功标签](figures/main8000/alignment_depth.png)

## 7 数据采集与现有加载器验收

复用已有双视角RGB与动作状态采集器，新增独立V0_demo03元数据和几何记录。每条轨迹保存配置、初态、资产哈希、动作、状态、接触、阶段、独立评分和仿真/墙钟时间。obs是动作前状态，action是7个绝对臂关节目标加左指位置目标，当前右指另一路下发相同值，next_state是4个物理步后的后继状态；控制间隔1/60秒。agent_pos第8维是左指实际位置，不是总开度或双指平均；夹指指令单位米，臂关节单位弧度。8维action不包含阶段化夹指effort上限；该上限在physics_records和本轮CSV/NPZ中逐步对齐保存，H5另有phase_code。物理回放或后续策略评估须复用同样的阶段控制和上限，不能仅凭8维关节目标就声称完整复现了支撑交接。

主片seed8000共3707个控制转换、14829条物理状态。现有MinimalPickDataset实际读取合格索引，得到双RGB[1,3,256,256]、agent_pose[1,8]、actions[1,16,8]与is_pad[1,16]，动作均有限。来源A1、目标candidate_far_hinge、asset hash、阶段和成功过滤逐项核对。正式15条共55,609个控制转换，逐步动作、实际关节、阶段、装配关系及时间对齐均验收通过；独立合格索引实际链接15条并读出batch，前后15份H5的SHA保持一致。原中断H5未作为数据集打开。详见 [最终15条验收](data_audit/final15_20261020_01/acceptance.json)。未开展ACT、Diffusion、VLA、RL或任何优化器训练。

阅读包保留一个约360KB的真实batch样例，取14秒EXTRACT和33秒INSERT两个时点；动作逐元素与源H5一致，图像反量化逐像素一致，可用numpy allow_pickle=False读取。这是两个真实batch样本，不是完整episode。完整H5、双视角图像和接触全量留在独立outputs；完整控制时序另提供精简CSV；最终主片与本节主样例同源于seed8000，开发首条成功dev_03的样例另保留。见 [加载验收](data_audit/random8000_actual_loader.json)、[样例说明](data_audit/main_sample_data/README.md)。

privileged/progress是缓存转换时采样的控制器进度；末次VERIFY判决发生在最后一次缓存之后，不能把最后采样stable=false补写为true。最终稳定资格由真实3.1秒物理窗口独立判断。原始result.json保留控制器的保守资格字段，不回写；最终任务/数据资格以independent_score.json、adjudication.json、execution_summary.json和H5属性为准。native_pair_success与real_calibrated为false；适配模式不要求这两个字段为true。适配成功样本不进入原CAD配套或历史完整装载成功索引。

## 8 复现和结果位置

代码分支codex/lab-cuvette-demo03。固定复测基线f15a757d57fafc5690a07df0e20e565b91d5c24d；随机运行提交b649fb943db7e46f2eba76bc3082580434485243。控制、采集和物理逻辑按源码核对一致，仅主展示相机拓宽；每条provenance保留文件SHA及当时工作区状态。

原始结果根目录为 /home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03。首条开发成功位于 dev_03/trial_00，最终完整视野主片位于random10_20261020_01/seed_8000/trial_00，开发失败位于dev_01与dev_02；固定和随机批次分别位于fixed5_20261020_01和random10_20261020_01；后两条完整随机记录在random_recovery_20261020_01，原seed8008中断目录保留。完整H5在每个trial的dataset/episode_0000.h5。输出目录要求不存在，避免覆盖旧结果。

```bash
cd /home/wujing/Desktop/vla/LabSim
# GUI 单次完整演示；添加 --headless 可无窗口运行
bash demos/lab_cuvette_demo03/run.sh \
  --output outputs/lab_cuvette_loading/V0_demo03/my_demo
```

```bash
# 重现主片seed8000的槽位和装配扰动
bash demos/lab_cuvette_demo03/run.sh --headless --random-layout \
  --seed 8000 --output outputs/lab_cuvette_loading/V0_demo03/my_seed8000

bash demos/lab_cuvette_demo03/run_fixed.sh \
  outputs/lab_cuvette_loading/V0_demo03/my_fixed5
bash demos/lab_cuvette_demo03/run_random.sh \
  outputs/lab_cuvette_loading/V0_demo03/my_random10 \
  outputs/lab_cuvette_loading/V0_demo03/my_fixed5/summary/episodes.json
```

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.data_check \
  --episode <成功trial目录>/dataset/episode_0000.h5 \
  --score <同一trial目录>/independent_score.json \
  --output outputs/lab_cuvette_loading/V0_demo03/my_data_check
```

新代码、配置及派生USD见 [任务说明](../../../demos/lab_cuvette_demo03/README.md)。[GitHub分支](https://github.com/zez2001/LabSim/tree/codex/lab-cuvette-demo03)为私有仓库，需要访问权限。最终交付提交及每份文件SHA由新阅读包的文件清单记录，避免将报告自引提交当作运行基线。

## 9 历史保护与剩余校正

开工前基线覆盖旧版本6067文件，真实SHA重读全部一致；另对demo02基准a008a188的108个受管文件做Git内容或LFS实体核对，全部一致。demo02的42个ignored输出当前存在，但没有开工前逐文件哈希，其历史逐字节保护状态为未知；没有把当前存在性当作完整哈希证明。本地与远端main均保持8df72784265c375a327ffa3f0a0cf8c676f229a7。

仍需集中补充三类实测资料：白架净槽、深度、壁厚及抓取露出；原器皿与A/B全深度配合尺寸、承托高度、插入方向及配套型号；器皿质量/材料/质心、夹爪摩擦与机器人驱动响应，以及开盖姿态和相机标定。它们用于后续实物校正，不阻塞已明确范围的video_demo_adapted仿真任务。

本轮结论限定为当前参数化架、派生A座、控制和物理配置下，是否能够在视频对应场景完成连续物理装载并生成可读数据。它不证明原CAD已经配套、实物装载必然成功或Isaac Sim具有某个真实亚毫米精度。

## 10 证据入口

[最终主录像](media/random8000_full_view/main_h264.mp4) · [同次腔内近景](media/random8000_full_view/closeup_h264.mp4)

[来源取出片段](media/random8000_full_view/source_extraction.mp4) · [支撑交接近景](media/random8000_full_view/insertion_handoff_closeup.mp4) · [松爪撤离及稳定](media/random8000_full_view/open_retreat_stability_closeup.mp4)

[开发失败代表录像](media/dev_01_failure/main_h264.mp4) · [入口受阻与滑移诊断](data_audit/dev02_contact_diagnosis/README.md)

[资产对应表](asset_correspondence.csv) · [最终尺寸表](dimensions.csv) · [来源及修改](asset_changes.json)

[18条完整结果及1条中断](results/final/results.csv) · [全部独立判分与版本证据](results/final/README.md) · [全部15条数据验收](data_audit/final15_20261020_01/README.md)

[主片完整控制时序](data_audit/random8000_trajectory/control_trajectory.csv) · [真实batch样例](data_audit/main_sample_data/README.md) · [实际加载结果](data_audit/random8000_actual_loader.json)

[历史保护检查](preservation_final_verification.md) · [整臂计划检查](evidence/arm_plan_03.json) · [控制源码冻结核对](evidence/control_freeze_verification.json)
