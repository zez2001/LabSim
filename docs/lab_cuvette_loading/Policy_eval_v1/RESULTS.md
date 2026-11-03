# LabSim 器皿装载策略量化评测

GPT 6 Astra direct P9 与 RLinf Pi05 LIBERO 冻结方案  固定standard场景  2026年11月3日

## 结论概览

两套冻结方案均已真实执行，但本轮没有完成从来源架到腔内放稳的完整装载。GPT首集完成物理抓持、离架及持物横移，随后主动结束；第二集受原API费用预留限制截断。π0.5两集均未建立有效抓持，因手掌与仪器接触而安全终止。

| 执行方案 | 计划 / 启动 | 环境有效 / 记录完整 | 完整成功 | 95% Wilson区间 |
| --- | --- | --- | --- | --- |
| GPT-6 direct P9 | 10 / 2 | 2 / 2 | 0 / 2 | 0.000%–65.762% |
| π0.5 LIBERO RPC | 10 / 2 | 2 / 2 | 0 / 2 | 0.000%–65.762% |

每组仍有8集未启动。按事先固定的成对规则，GPT02费用终止后完成π0.5配对集，再停止后续计划；未启动集没有进入分母。另有6条已闭合接口诊断，全部独立保存，不混入正式结果。

端到端成功率分母包括全部已启动正式集；当前环境有效且任务可评估子集也各为2集，因此两种口径同为0/2。GPT02仍标记为预算截断；该记录说明当时未完成任务，不能推断若继续运行必然失败。成功完成时间样本n=0，结果为N/A。

结果仅描述同一standard布局下两套当前执行方案。输入信息、原生工具与动作chunk不同，且样本量很小；当前证据不足以比较通用模型能力或估计跨场景成功概率。原资产、控制器、物理配置、reward、独立scorer与数据资格规则保持基线。

## 任务场景与冻结环境

任务链为来源架抓取、拔出、搬运、内部座对准与插入、支撑交接、松爪、实际脱指和撤离，并保持至少3秒稳定。原独立scorer裁定完整任务结果；Progress v1.2提供物理阶段、有效连续量及未完成原因。

| 项目 | 实际冻结值及来源 |
| --- | --- |
| 版本与模式 | Project_release_v1 / lab_cuvette_loading / standard；场景及资产、光照、物理随机化关闭 |
| 器皿与质量 | cuvette_xy_1000；10×10×67.5 mm尺寸假设；20 g工程质量 |
| 来源和目标 | 完整6×6白色架A1，远角F6蓝色器皿；单台开盖仪器内部A座 candidate_far_hinge |
| 目标深度 | 27 mm；原座几何保持不变 |
| 频率与时间上限 | 物理240 Hz；控制60 Hz；共同任务仿真上限170 s |
| 相机 | 侧视与腕视原生640×480 RGB；H5单独记录256×256 CHW；相机安装保持标准配置 |
| HF资产revision | bb880f098180c291f6f65995f969d48047207067 |
| 运行源码 | 3ca253324b1ec540ae5ec07f2110c9c091f6ddd1 |
| 共同场景指纹 | 171b188da73904f2a77d6232be63f8beb95323f75e6886f81df76fee9ae16a37 |

复用上一轮完整Teacher成功证明任务在相同物理配置下可执行，本轮未重复运行Teacher。上下文审计确认四集与Teacher的资产、布局、物理及执行参数一致；契约哈希差异来自truth_teacher与collect/eval记录用途，未发现其他配置差异。

四集实际首次动作前的TCP、关节及器皿初态按保存值比较均一致，布局指纹相同；这些是当前仿真数值一致性记录，不是实物标定或真实精度证明。

## 模型身份和实际输入动作

| 方法项 | GPT direct P9 | π0.5 RPC |
| --- | --- | --- |
| 实际模型 | 请求及返回gpt-6-astra；Cubence /v1/responses；显式P9配置，非旧默认P4 | RLinf-Pi05-LIBERO-130-fullshot-SFT |
| 训练及身份范围 | 供应商声明模型标识一致；中转后权重与训练数据未知；本轮无新训练 | 本地LIBERO-130 fullshot SFT，权重SHA固定；本工程无LabSim微调，上游完整语料成员关系未知 |
| 视觉 | 两路640×480 JPEG质量60/high；固定侧图裁剪放大；最多一张历史腕图 | 两路[1,480,640,3]uint8；processor保比例缩放补边至224，再float归一化到−1..1 |
| 机器人状态 | q9/dq9、actual TCP、夹爪及公开接触；附robot-only FK/自身盒信息 | 基座系TCP xyz+rotvec及左右指状态共8维；原q01/q99标准化后补零32维 |
| 文本和上下文 | reasoning=low；输出1024tokens；最近完整工具回执上下文；逐集清空 | 实际137次processor输入均264→200tokens；完整核心任务前缀保留，静态TCP四元数尾部与净空提醒被截 |
| 原生动作 | observe / move_ee / gripper / wait / finish；世界或TCP系m/rad通用工具；动作0.05–3s | 输出float32[1,5,7]；horizon10、执行chunk≤5；20Hz每行.05s |
| 动作执行 | 连续IK、实际跟踪、接触锁存；模型自主选择动作与终止 | 原LIBERO OSC反归一化后裁至[-1,1]，.05m/.5rad映射再限每轴.5mm/.004rad，夹爪±.008m，8N |
| seed与等待 | 策略seed未发送；每集新工具和空对话；推理时物理暂停 | 每集新模型/adapter，Torch seed0；环境seed0另记；推理期间核对episode/step/time不变 |

器皿动态真值位姿、精确目标误差、Teacher waypoint、Progress与scorer没有自动送给两组策略。GPT比π0.5多了显式工具、公开触觉及机器人自身几何等信息；本轮比较冻结端到端方案，不将两者改造成统一动作策略。完整prompt、tool schema、checkpoint及归一化SHA见身份文件。

## 正式协议和逐集结果

按GPT01→π01→GPT02→π02顺序运行，逐集独立reset且仅驻留一个Isaac任务。共同任务预算是170秒仿真；GPT每集最多160次逻辑调用、策略墙钟1800秒；π0.5最多700次推理、3500动作。单请求及监督器保护另按协议固定，未人工接管或Teacher补全。

| trial | 仿真s | 控制步 | 最远物理达成 | 原终止原因 | 解释 |
| --- | --- | --- | --- | --- | --- |
| gpt6_01 | 62.017 | 3720 | 持物横移50 mm | POLICY_FINISH_REQUEST | 正常评分 |
| pi05_01 | 16.867 | 1011 | 未确认抓取接近 | ROBOT_ENVIRONMENT_COLLISION | 正常评分 |
| gpt6_02 | 12.517 | 750 | 未确认抓取接近 | COST_BUDGET_EXHAUSTED | 预算截断 |
| pi05_02 | 17.150 | 1028 | 未确认抓取接近 | ROBOT_ENVIRONMENT_COLLISION | 正常评分 |

四条正式记录均闭合、环境有效、记录有效且task_success=false。主分母包含服务、预算和安全终止；本轮没有把系统终止移除以抬高成功率。有效任务子集未排除任何正式集；GPT02保留censored=true以便后续有足够预算时另作独立条件研究。

| GPT01里程碑 | 首次确认仿真时间s | 首次候选至确认等待s |
| --- | --- | --- |
| 接近抓取区域 | 18.112500 | 0.000000 |
| 有效抓持 | 18.112500 | 0.100000 |
| 完全离架 | 19.820833 | 0.000000 |
| 持物横移50 mm | 43.170833 | N/A |

上表等待时长是候选证据持续到确认的等待，不是子任务执行总时长。未达成阶段时间保留not_reached/N/A，未将0秒放入均值。持物横移50mm由原scorer物理证据确认，与到达固定预插入区分开统计。

## 阶段达成率与每集最远阶段

![阶段按物理历史首次确认统计；每组分母2，所有阶段unknown=0，控制端点证据覆盖率100%。](results/analysis/figures/01_stage_rates.png)

![GPT01最远达到持物横移50mm；其余三集没有确认接近抓取阶段。](results/analysis/figures/02_episode_farthest_stage.png)

GPT组的接近、有效抓持、完全离架及持物横移均为1/2；到达固定预插入区及之后全部为0/2。π0.5各阶段为0/2。已达成阶段比例的95% Wilson区间为9.453%–90.547%，未达成阶段为0.000%–65.762%，必须结合原始计数阅读。

全部控制端点没有证据gap，因而此处not_reached是有覆盖证据下没有确认达成；unknown数量另行输出。阶段完成不推出完整任务成功，原独立评分仍要求支撑、脱指、撤离及3秒稳定。

## 终止原因和实际动作执行

![GPT分别为主动提前结束和费用预算结束；π0.5两集均为原安全碰撞终止。](results/analysis/figures/03_termination_types.png)

| trial | 返回动作数 | accepted/回执 | 发生限幅动作 | 部分执行 | 执行异常 |
| --- | --- | --- | --- | --- | --- |
| gpt6_01 | 32 | 32/32 | 0 | 0 | 0 |
| pi05_01 | 340 | 337/337 | 337 | 0 | 0 |
| gpt6_02 | 6 | 6/6 | 0 | 0 | 0 |
| pi05_02 | 345 | 343/343 | 343 | 1 | 0 |

accepted表示执行器接受请求，不是任务动作正确率。π0.5全部实际请求均有既有迁移限幅；这是冻结adapter的数值转换，不是新增补救。返回chunk尚未执行的尾部在安全终止后丢弃，未重放。π02最后一行仅执行两个控制周期，保留partial记录。

| 碰撞集 | 首次接触s | 终止s | 原始事件数 | 末事件单点力模N |
| --- | --- | --- | --- | --- |
| pi05_01 | 16.866667 | 16.866667 | 1 | 29.677 |
| pi05_02 | 17.137500 | 17.150000 | 4 | 23.838 |

两次接触均定位为 /World/Franka/panda_hand/geometry/panda_hand 与 /World/Instrument/Collision/SourceMesh2。原callback冲量按当前physics_dt换算，表内是末事件最大单点原始向量模，不是器皿支撑净力，也未跨事件或接触点累加。碰撞属于策略/安全表现，未改标为环境无效。

## 连续Progress轨迹与未完成要求

![四条真实正式轨迹的历史覆盖和有效插入进度；横轴为仿真秒。历史覆盖为诊断量，不是累计reward或完整成功率。](results/analysis/figures/04_representative_progress.png)

GPT01阶段覆盖在抓持和离架后上升，但固定预插入区未达成，Progress未完成原因为TRANSPORT_NOT_COMPLETED。有效插入进度始终为0；另外三集同样没有有效插入。分析消费完整progress_events.jsonl，包含GPT01结束时的attempt_ended finalize事件；其余三集尚未启动抓持尝试，事件数为0，逐步记录仍完整。

GPT01只有1次抓持尝试，0次重试；其他集为0次尝试、0次重试。完整便携HTML保留全部原始控制端点、有效门控、单独单位曲线及真实视频时间映射，便于进一步核查。

## 真实双视角代表画面

![GPT01 实际抓持帧，t=18.116667s；episode 51abe385-697e-4a22-92a6-f24659929d8f。](results/frames/gpt6_01_01_grasp.png)

![GPT01 结束时仍夹持器皿，未放入目标；t=62.016667s。](results/frames/gpt6_01_03_terminal.png)

![π01 安全停止帧，t=16.866667s；episode 072eb1fc-d7ae-4a79-9e97-8986bac3856c。](results/frames/pi05_01_03_terminal.png)

选择规则为展示唯一达成抓持/搬运的GPT01与π01典型安全终止，未仅挑选最佳终态。GPT02费用截断和π02重复碰撞的完整视频同样提供；四集均进入主表。截图按原video_timestamps最近真实帧选取，没有生成或插值运动。

## 适用区间内的精细量和抓持漂移

![进入目标操作区的适用样本数为0；目标横向/姿态误差、有效深度及释放后稳定保持N/A，不把未达目标误写为0mm。](results/analysis/figures/05_applicable_target_metrics.png)

| 区间 | 相对平移mm | 相对转角rad | 样本数 | Hz |
| --- | --- | --- | --- | --- |
| GPT01 全操作 | 0.003565 | 0.000118074 | 10538 | 240 |
| GPT01 首次目标承托前 | 0.003565 | 0.000118074 | 10538 | 240 |
| 所有集支撑交接 | N/A | N/A | N/A | N/A |
| 其他三集抓持漂移 | N/A | N/A | N/A | N/A |

| trial | 最近接近诊断mm | 目标区样本 | 最大有效进度 | 有效深度 |
| --- | --- | --- | --- | --- |
| gpt6_01 | 6.725 | 0 | 0.000 | N/A |
| pi05_01 | 223.670 | 0 | 0.000 | N/A |
| gpt6_02 | 199.699 | 0 | 0.000 | N/A |
| pi05_02 | 224.298 | 0 | 0.000 | N/A |

最近距离为实际TCP到当前器皿位姿变换后的配置抓取参考点的最小距离。原core在held=true时也确认approach阶段，该规则不改变距离数值；GPT01的6.725mm不能解释为固定来源抓取点误差或机器人精度。漂移以实际杯在手坐标的固定参考计算，包含杠杆臂转动，未按抓持质量过滤。GPT01无目标承托，故全操作与承托前区间相同；独立原物理记录复算已通过。上述微小漂移是当前仿真相对运动，不是真实器皿或平台精度。

## 推理延迟墙钟与费用

![逐集先汇总再等权比较；GPT是HTTP端到端请求耗时，π0.5是adapter RPC predict，模型forward另行记录。](results/analysis/figures/06_latency_and_wall_time.png)

| trial | 模型调用 | 推理合计s | 每调用均值s | 整集墙钟s | 估算USD |
| --- | --- | --- | --- | --- | --- |
| gpt6_01 | 33 | 258.003 | 7.818 | 895.067 | 1.049828 |
| pi05_01 | 68 | 11.204 | 0.165 | 279.053 | N/A |
| gpt6_02 | 6 | 53.264 | 8.877 | 220.022 | 0.193282 |
| pi05_02 | 69 | 11.664 | 0.169 | 284.054 | N/A |

正式GPT共39次实际网络调用，返回输入/输出token合计482033/5870，估算USD1.243110；另5次诊断GPT调用估算USD0.130436。账本累计377次、USD29.267746，原上限USD30.00，剩USD0.732254。余额不足下一请求的保守预留，触发原预算保护；未提高额度或重建账本。

π0.5本地模型两集forward合计分别7.932和8.291秒；模型进程Torch峰值allocated均为7,644,988,416 bytes，非整GPU/Isaac总显存。电力及本地运行费用未测量，费用为N/A。

墙钟包含环境/模型启动、reset、推理、动作、记录导出和退出。推理与网络等待期间物理暂停，仿真时间不含推理等待。服务队列等待不能独立分离，保留N/A；本地usage×费率是费用估算，供应商真实账单和账户倍率未知。两组任务均未成功，不能用较短终止墙钟宣称完成任务更高效。

## 完整性复现与后续研究

四集原H5、动作后继邻接、时间戳、闭合标记、完整Progress、原始视频解码均通过独立核验。当前CPU仓库检查1235passed/5skipped；跳过为现CPU解释器缺少4项RPent与1项pxr依赖，相关真实模型/Isaac链路已在各自隔离环境运行。评测专项检查42passed。

四集由正常发布版ACT及DP failure读取入口全部读出实际finite batch：ACT图像[3,3,256,256]，DP图像[3,3,3,256,256]，动作均[3,16,8]。H5及原标签前后哈希一致；成功BC资格全为false，没有生成训练样本冒充成功，也未执行训练。

| trial及汇报包视频 | 完整episode_id | 原H5 SHA256 |
| --- | --- | --- |
| gpt6_01<br>media/gpt6_01_dual.mp4 | 51abe385-697e-4a22-92a6-f24659929d8f | f359cbdb7638a99b65556b0996849e63bf4c0ed1d7c2bf47ad4502181e4bc62c |
| pi05_01<br>media/pi05_01_dual.mp4 | 072eb1fc-d7ae-4a79-9e97-8986bac3856c | bd08fc40867e1e67ee82cfcf4de1dd8f5b9a1408f1bc85db7d6c1770593f1a15 |
| gpt6_02<br>media/gpt6_02_dual.mp4 | 57a3dcad-591f-4b39-8d99-6d9c53fc1d67 | f29baa59a2e4f45d032834b0c3c7c2208a123cd8bb6b0b526cbad2de44fef0c5 |
| pi05_02<br>media/pi05_02_dual.mp4 | aa17c728-5239-40f1-a0e4-46f79a1dad22 | b23ee24bd9d0d3dd93b202432a5e5c2b10a61c17808065ca933e8364aebcae59 |

实际策略/仿真源码3ca253324b1ec540ae5ec07f2110c9c091f6ddd1；分析源码094f8a18ecf0858dee4b8c86e9133c7275520995。报告生成与最终发布另由publication.json及SHA清单绑定，测试后的文档/包装变更单列。原始大型H5定位为工程outputs/lab_cuvette_loading/Policy_eval_v1/20261103/formal_{trial}/environment/episode_0000/dataset/episode_0000.h5。

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.analysis /absolute/path/to/metrics_final_01/trials.json --output /absolute/path/to/new_analysis
"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.plots /absolute/path/to/new_analysis/summary.json --manifest /absolute/path/to/metrics_final_01/trials.json --output /absolute/path/to/new_figures
```

当前关键结果是GPT可以建立一次物理抓持并离架搬运，原LIBERO π0.5迁移方案在此任务中提前碰撞，两组均未展示腔内装载能力。后续研究应先独立声明更充足预算、输入与动作迁移研究条件，再比较可达性/整手避障、目标区视觉对准和完整卸载行为。当前结果不支持通用模型排名、真实精度认证或跨布局成功率结论。

## 证据与版本入口

[冻结协议](../../../config/lab_cuvette_loading/Policy_eval_v1/protocol.json)、[GPT 身份](gpt_identity.json)、[π0.5 身份](pi05_identity.json)、[公开输入与原生动作](input_contracts.md)、[π0.5 processor 与执行](pi05_input_contract.md)。

工程反馈包中的 summary.json、episodes.csv、stage_rates.csv、逐集闭合凭据及完整 Progress 可复算本报告。汇报包的 media/ 目录包含下文命名的四段连续视频。大型 H5 和真实模型输入留在工程端，身份及 SHA256 在表中给出。最终提交、远端与 CI、历史保护核验见反馈包 publication.json 和 protection_final.json；其结果在发布时生成，不提前标为已通过。

## 完整连续录像与便携复算

本次四条正式轨迹的完整双视角视频：

- [gpt6_01_dual.mp4](../../../outputs/lab_cuvette_loading/Policy_eval_v1/20261103/media/gpt6_01/gpt6_01_dual.mp4)
- [pi05_01_dual.mp4](../../../outputs/lab_cuvette_loading/Policy_eval_v1/20261103/media/pi05_01/pi05_01_dual.mp4)
- [gpt6_02_dual.mp4](../../../outputs/lab_cuvette_loading/Policy_eval_v1/20261103/media/gpt6_02/gpt6_02_dual.mp4)
- [pi05_02_dual.mp4](../../../outputs/lab_cuvette_loading/Policy_eval_v1/20261103/media/pi05_02/pi05_02_dual.mp4)

[正式分析JSON](results/analysis/summary.json)、[逐集CSV](results/analysis/episodes.csv)、[阶段CSV](results/analysis/stage_rates.csv)保留最终分析02的原始结果。`results/metrics/trials.json`保留原机器身份与绝对定位；另提供[派生便携清单](results/portable_trials.json)及[来源绑定](results/source_binding.json)。

在工程反馈包根目录，以已有Python 3.11与NumPy运行：

```bash
PYTHONPATH=code python code/docs/lab_cuvette_loading/Policy_eval_v1/tools/reanalyse_portable.py \
  --package-root . --output /absolute/path/to/NEW_RECOMPUTATION
```

该入口用包内原result/资格JSON与完整Progress复算逐集指标、分母、Wilson区间和分组结果，并与最终分析02核对。gzip9转移副本先按便携凭据验证存储SHA及解压JSONL SHA；只在新输出中的派生工作summary更新存储表示的SHA/byte数，所有非存储字段保持相同，包内原summary不改。它不打开大型H5、不重跑物理scorer或策略，也不能代替工程端的H5结构、原物理/接触数据或cooked碰撞几何核验。
