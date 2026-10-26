# LabSim Project v1 项目发布与验证报告

发布日期 2026年10月26日　分支 codex/labsim　面向组内使用与后续策略评测

Project_v1已完成公开资产获取、同机干净checkout的完整teacher演示、统一接口与新数据闭合。固定standard场景teacher正式5/5成功。GPT已实际完成图像闭环和冻结配置5次尝试，未取得完整成功：1条有效抓持滑移失败，4条物理无效且任务结果未知。

## 当前正式任务

默认入口为 lab_cuvette_loading / Project_v1 / standard。Franka 从完整白色6×6来源架的A1取出10×10×67.5 mm尺寸假设器皿，放入单台仪器内的原始A座，完成插入、支撑交接、开爪、退让与至少3秒独立稳定。质量20 g；布局、初始化、资产和场景随机化均冻结。原座及历史V0、Env_v1、Size_v1保持独立。

## 本轮实际执行结果

| 后端与范围 | 成功数 | 仿真秒 | 墙钟秒 | 控制步 | 结论 |
| --- | --- | --- | --- | --- | --- |
| teacher GUI | 1/1 | 105.82 | 851.96 | 6348 | 完整装载并稳定3秒 |
| teacher headless | 5/5 | 105.82/集 | 874.25-934.01/集 | 6348/集 | 同进程5集均实际支撑、脱指、退让及稳定3秒；进程总4477.79秒 |
| 新受控失败 | 0/1 | 66.37 | 496.55 | 3981 | 5 mm插入阈值受控停止；记录有效，未开爪或退让，不是自然失败 |
| GPT 正式5次 | 0/5尝试 | 合计97.75 | 合计1413.15 | 5860 | 0完整成功；1有效抓持滑移失败，4物理无效且任务结果未知 |
| π0.5 / Harness | 各0/1 | 各0.25 | 6.48 / 86.92 | 各15 | 各5个模型动作，尚未抓取 |

teacher使用真值控制，GPT读取两路图像、机器人自身状态、相机标定和允许的指端接触反馈。各后端共用任务、记录器与独立评分；结束请求、正常退出或接口连通不代表成功。墙钟采用episode结果值，π0.5/Harness为适配回路；含启动的进程时间另见执行证明。

![本轮GUI teacher完整同一次运行，105.8167秒，独立测得退让后3秒稳定窗结束。图像属于d09c5ff代码与75d288场景指纹，和正式重复评测快照分开保存。](../media/06_final_stable.png)

[完整teacher双视角录像 105.83秒](../media/teacher_full_continuous.mp4)

[GPT调试03完整尝试 26.13秒 物理无效](../media/gpt_pilot03_full_attempt.mp4)

[GPT正式第4次完整尝试 29.43秒 抓持滑移失败](../media/gpt_formal04_of05_full_attempt.mp4)

## 从干净 checkout 开始使用

已验证环境为Linux、Isaac Sim 5.1.0.0、Python 3.11.16、Torch 2.7.0+cu126、NumPy 1.26.0、h5py 3.15.1、OmegaConf 2.3.0与RTX 4090。复用本机已安装的Isaac环境；Shapely 2.2.0由独立site-packages注入，未修改Isaac或既有模型环境。原生task、factory、controller和collector已注册，./labsim与正常任务入口共享实现；安装细节见仓库接入指南。

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim \
  https://github.com/zez2001/LabSim.git
cd LabSim
git checkout 7a7cbb81c6fcede84b48d1e9b60f66c68dfac0f0
export LABSIM_PYTHON=/absolute/path/to/isaac-python
export LABSIM_GEOMETRY_SITE=/absolute/path/to/geometry/site-packages
./labsim assets download
./labsim doctor
./labsim demo --task lab_cuvette_loading --scene standard \
  --backend teacher --gui --output outputs/project_demo_001
./labsim eval --task lab_cuvette_loading --scene standard \
  --backend teacher --episodes 5 --headless \
  --output outputs/project_teacher5_001
```

headless演示将 --gui 换为 --headless。输出目录必须全新；下载器默认使用用户缓存，也可设置LABSIM_ASSET_CACHE。doctor检查真实依赖、路径和资产状态，但CPU预检通过不能代替GPU物理验收。

## 采集 读取与 GPT 评测

```bash
./labsim collect --task lab_cuvette_loading --scene standard \
  --backend teacher --headless --output outputs/project_collect_001
./labsim dataset-check --path outputs/project_collect_001/episode_0000 \
  --sample-filter success --policy both --output outputs/read_001.json
./labsim collect --task lab_cuvette_loading --scene standard \
  --backend teacher --controlled-stop-depth-mm 5 --headless \
  --output outputs/project_failure_001
for attempt in 0000 0001 0002 0003 0004; do
  ./labsim eval --task lab_cuvette_loading --scene standard \
    --backend gpt6 --episodes 1 --headless --max-calls 160 \
    --budget-ledger outputs/cubence_budget.json \
    --output "outputs/gpt5_${attempt}"
done
```

先在本地终端设置CUBENCE_API_KEY。provider固定为Cubence、https://api.cubence.ai/v1、Responses API与gpt-6-astra。探针、调试、重试和正式评测共享预算ledger；已有ledger不应删除以重置预算。错误类别包括任务失败、模型服务失败、协议错误、预算结束与仿真异常。

## 同机新目录复现范围

已从公开codex/labsim代码建立同机新目录，运行资产来自无凭据、空缓存的固定revision公开下载；复用已验证的Isaac安装。GUI完整teacher在d09c5ff代码上真实成功；正式headless评测在43649a2代码上单个Isaac进程连续5集，随后另采1条5 mm受控失败。6集实际初始关节、夹指及器皿位姿完全一致，确认连续reset及重新启动恢复。

CPU契约214通过、1跳过；最小CPU环境缺h5py的样例测试，已由真实Isaac环境的H5读取另行验证。6集teacher/受控失败各22项审计与ACT/DP读取通过；全部进程关闭后才打开H5。7a7cbb运行代码已推送，GitHub CPU contracts于run 40317505769完成且success；CPU与GPU结果分别记录。

## GPT 直接控制与全部尝试

Cubence Responses API的文本、实际相机图像、结构化工具与多轮反馈已真实验证；请求与返回模型名为gpt-6-astra，未独立认证底层模型身份。原始640×480 PNG曾超时；512×384 JPEG low通过。1次high-detail响应缺模型名，另列为身份未确认，不推断发生模型替换。

正式5次为5个顺序关闭的单集Isaac进程，使用同一冻结模型、提示词、工具、限幅、评分与standard场景，期间未调参。图像最长边512、JPEG质量60、detail=low。独立进程用于存储保护，场景未随机化；控制器完整SHA见末页。

模型只用通用末端、夹爪、等待、观察和finish工具，不使用专家宏或teacher轨迹。动作绑定episode、observation和action ID；越界/过期指令拒绝，重复ID查询回执。请求期间暂停物理，完整解析验证后才执行。

| 尝试 | 请求 | 动作 | 仿真秒 | 墙钟秒 | 结果与最远阶段 |
| --- | --- | --- | --- | --- | --- |
| 调试01 | 4 | 0 | 0.02 | 62.4 | 本地上下文保护；3拒绝加1观察，0运动，任务未知 |
| 调试02 | 6 | 5 | 8.87 | 121.0 | 环境碰撞；未抓取，任务未知、记录无效；末动作仅0.85秒 |
| 调试03 | 14 | 14 | 26.12 | 418.5 | 曾接触、抬升和离架，后位姿跳变；未稳定抓取或搬运，任务未知 |
| 正式01 | 13 | 12 | 23.98 | 300.1 | 环境碰撞安全停；未离架，任务未知、记录无效 |
| 正式02 | 4 | 4 | 6.08 | 89.1 | 控制或IK部分执行后安全停；3完整加1部分，任务未知、记录无效 |
| 正式03 | 3 | 3 | 5.92 | 103.0 | 控制或IK部分执行后安全停；2完整加1部分，任务未知、记录无效 |
| 正式04 | 18 | 16 | 29.42 | 492.0 | GRASP_SLIP有效任务失败；曾离架，未搬运，task=false |
| 正式05 | 17 | 17 | 32.35 | 429.0 | 曾离架后环境碰撞；任务未知、记录无效，未搬运 |

请求数含失败与重试；动作列为实际执行指令，含部分执行，观察/结束与拒绝另计。墙钟为episode结果值，模型等待时物理暂停。调试尝试未并入正式5次结果。

正式55次请求均返回匹配模型名；无服务失败或预算结束。5次中2次环境碰撞、2次已知控制或IK部分执行后停机，均保留task_success=null、record_valid=false；第4次为有效GRASP_SLIP失败。曾出现接触、抬升和离架事件，但grasp_success/transport_success均未通过；没有插入、释放、退让或装载稳定成功。55份实际公开输入JSON、110张传输JPEG、动作时序与暂停区间核验通过。

全部探针、3次调试与5次正式尝试共95次网络请求；正式55次。返回usage累计446950输入token（含11392缓存）和14496输出token，按配置价格估算5.091772美元；7次超时未知usage保守预留0.702690美元，预算占用合计5.794462美元，正式部分3.656570美元。未耗尽30美元/1500次上限。5次重试、无HTTP429；参数错误探针仅超时，未验证400/422拒绝。以上不是供应方实付账单。

## 动作约定与公平性

GPT末端动作以米、弧度、wxyz四元数记录，world/TCP与绝对/增量语义显式，夹爪为双指总开口。单次上限0.04 m/0.15 rad、0.05至3秒，速度上限0.02 m/s与0.15 rad/s。每指上限8 N；运动默认8 N，夹爪工具可显式选0至8 N，不按teacher阶段或真值自动调力。记录值是驱动上限，不是实测接触力。ACT/DP为7臂关节绝对目标加单指位置，9维实际双指命令另存。

## 公开资产与许可边界

公开HF Dataset为Txie000/SLAI-Labsim。运行资产包含器皿原模型、35个横向尺寸派生体、仪器、来源架、配置元数据、来源及参数假设；视觉和碰撞对应、单位、坐标轴、根节点、质量、质心、惯量、摩擦与逐文件哈希见manifest和资产锁。公开USD仅清除非运行文档字段中的作者目录，43个USD语义比较通过，历史源文件与物理参数未被改写。

| 发布内容 | 固定 revision | 文件与大小 | 实际验证 |
| --- | --- | --- | --- |
| 运行资产 | bb880f098180 | HF任务文件82个；加外部机器人共83个 / 31,955,703 B | 独立无凭据进程、空缓存83/83；离线复用83/83 |
| 完整成功缩图样例 | 82317fe33089 | 5个文件 / 283,927,640 B | 匿名下载5/5；正常ACT和DP reader通过 |
| 样例发布后仓库总量 | 82317fe33089 | 174个 / 327,839,305 B | 增量发布，保留旧发布内容 |

项目所有者已确认所提供CAD与派生体的公开再分发授权，使用LicenseRef声明；该授权不等同于制造商许可。来源架与项目数值元数据按MIT声明。Franka文件许可仍未核实，因此没有重新上传HF；下载器从现有公开项目Git LFS固定提交取回相同哈希文件，来源与限制明确保留。

## 新旧数据与可移植性

历史20条成功与20条受控提前停止失败继续使用原Size_v1数据和正常ACT/DP读取器。本轮读取验证均通过，未重采整批40条、未改历史标签或指纹。失败数据是预设深度停止，不能解释为自然卡滞率。历史索引迁移需保留collection相对目录树。新Project_v1另采完整成功与受控失败，分别关闭并重新读取，详细结果见对应JSON。

公开样例来自本轮teacher GUI完整成功，保留全部6348个转换与末端观测，双视角256×256 RGB仅空间缩为96×96；没有时间抽样。动作、状态、事件、标签及时间戳数值保持不变，路径元数据规范为逻辑标识。H5无外部或虚拟数据依赖，正常reader按实际图像尺寸生成batch。96像素样例并非原生256像素训练数据，也不含高频物理JSONL和全部媒体旁文件。

本轮正式5成功和1条受控失败共35721个转换，全部6集逐集22项审计通过，并由正常ACT/DP reader分别重新打开。成功筛选接受5条；失败筛选只接受受控停止1条；all_valid接受6条。受控失败post_retreat_window不可用、stable_after_retreat未知；中止前terminal窗口stable=false单列，未补零或冒称已测退让稳定。完整H5与高频旁文件保存在本轮运行目录，未上传Git或初次HF发布。 GPT正式第4次的1764转换有效失败已通过正常ACT/DP读取，其余4条无效记录不作为合格任务失败或成功BC数据。未执行模型或优化器训练。

## 版本与关键证据入口

| 字段 | 版本或完整标识 |
| --- | --- |
| GPT正式代码 | 7a7cbb81c6fcede84b48d1e9b60f66c68dfac0f0 |
| teacher物理代码 | 43649a259112846bbc9b25acf2c3945b421a2281 |
| 任务与评分 | Project_v1.standard.v1 / Project_v1.independent.v1 |
| 动作接口 | Project_v1.actions.v1 |
| HF运行资产 | bb880f098180c291f6f65995f969d48047207067 |
| HF成功样例 | 82317fe33089aca5a20827da2adc592a1e0fdddc |
| GUI成功代码 | d09c5ffce2018702702eb0d4c77d862f1eae6faa |
| GUI场景指纹 | 75d288fe67e88c749cb578f36f3c246664b3e26d8455926bffbccf3576964de6 |
| 正式场景指纹 | a0f3cf36edd1472a7e7a3b88c9c9f745487523904ab8a9cede1637e49fee397e |
| GPT控制器指纹 | af2238443e8210b6b53243d297603c22ca4e8a654b415562a7c9dc8b726e2b85 |

原座局部原点与装载轴分别记录：装载目标使用原座坐标加[0.00065, 0.000001, 0] m，不再把局部原点[0,0]误写成目标轴。控制对准预算、判分容差与物理参数分开保存。评分要求真实抓取离架、搬运、目标支撑、脱指、至少0.04 m退让与3秒稳定；稳定窗位置漂移阈值0.0002 m、朝向变化1度，工程阈值不代表实物精度。

侧视与腕视名称直接进入正式配置和ACT/DP shape_meta。两相机采集640×480、60 Hz，正式训练读取RGB为256×256，GPT传输图像另按provider冻结的预处理配置；位姿、内外参、时戳和原始相机元数据随episode记录。GUI成功H5的6348条动作、图像、状态与后继时间对齐，8维训练动作与实际9维对称双指命令核验通过。

[teacher5与受控失败 逐集结果和关闭证明](../evaluation/standard5_and_controlled_failure_01_summary.json)

[GPT全部正式5次结果 真实输入与动作审计](../evaluation/gpt_formal5_01/formal5_summary.json)

[GPT全部调试与预算能力证据](../evaluation/gpt_formal5_01/budget_capability_summary.json)

[公开发布 固定revision与匿名下载摘要](../assets/release_status_summary_20261026.json)

[公开完整H5样例 匿名下载与ACT DP读取](../data/public_sample_anonymous_verification.json)

[已执行运行代码的GitHub CI结果](../validation/runtime_ci_actual.json)

## 剩余问题与后续工作

GPT仍未完成完整装载，且预算未耗尽，不能把结果解释为预算不足。下一版本需依据碰撞、控制/IK部分执行和抓持滑移证据改进通用控制与视觉反馈，再重新冻结评测；本轮不在正式结果中调参或由teacher接管。固定场景确定性5次重复不代表跨资产、随机布局或真机成功率。

本轮为同机新目录复现，尚未验证第二台机器。器皿尺寸、20 g质量、摩擦、来源架尺寸及机器人动力学仍是仿真假设，real_calibrated=false。保留原生速度与位姿差分不一致等告警；原座完整PhysX烹饪表示尚未全部读回。输入几何抽样和实际接触证据不能证明严格全局穿透上界，亦非0.1 mm真实精度认证。

运行代码7a7cbb81c6fcede84b48d1e9b60f66c68dfac0f0已推送，所对应GitHub CPU contracts成功。包含本报告的最终交付提交与远端核对由阅读包文件清单记录；运行代码、资产和评分对应关系以发布manifest为准。

[GitHub 发布分支](https://github.com/zez2001/LabSim/tree/codex/labsim)

[Hugging Face 公开资产与样例](https://huggingface.co/datasets/Txie000/SLAI-Labsim)
