# Project release v1 使用与验收

这是独立的 `Project_release_v1` 环境发布版本，物理任务继续使用 Project_v1_1 的固定 standard 场景、10 mm 比色皿、20 g 假设质量、原 A 座及已验证的执行器与评分器。历史结果不修改。本轮验收以环境是否能连续交互、闭合数据和正常读取为目标，不以策略装载成功率为门槛。

[项目快速开始](../../../README.md) · [生命周期和数据闭合](lifecycle.md) · [外部策略契约](external_policy/contract.md) · [物理基线 Project_v1_1](../Project_v1_1/README.md)

## 当前实际状态

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 代码与远端 | 冻结代码4a71635已推送且CI成功；物理素材核心122c4c0另记 | [当前GitHub实查](validation/github_4a71635_actual.json) |
| 干净checkout预检 | 4a71635实际doctor退出0、errors为空；这是CPU预检 | [实际doctor](validation/doctor_clean_4a71635.json) |
| 资产与独立缓存 | 固定revision，83文件hash通过；不新增资产 | 本轮发布清单补充实际缓存证据 |
| GUI与退出 | 官方CLI短程受控结束，退出0；旧菜单`get_stage_state`异常未出现 | [实际退出记录](validation/gui_finish_02_shutdown_actual_20261027/receipt.json) |
| GUI剩余问题 | `ManipulatorFactory`卸载回调仍有NameError；不是无错误退出 | 同上，保留完整日志扫描边界 |
| 单集数据闭合与读取 | GUI短集已闭合；底层读取和筛选检查通过；正式release入口另见clean修复后证据 | [闭合审计](validation/gui_finish_02_data_closed/summary.json) |
| 同进程三集 | **已实际闭合：成功 → 有效受控结束 → 成功** | [全量闭合审计](validation/same_process_collect_01_closed/summary.json) |
| 连续真实外部策略 | π0.5已执行69推理、341动作、17.017秒；安全碰撞终止 | [client闭合证据](external_policy/pi05_standard_01_client_closed/receipt.json)；环境已正常退出；[数据和正常读取](validation/pi05_standard_01_env_closed/summary.json)已核查 |
| 性能与体积 | 同口径完整episode减少39.9906%；不承诺提速 | [实际对比](validation/baseline_vs_collect_01_comparison/summary.json) |
| 资源 | 三集FD332与采样VRAM3591 MiB稳定；末RSS增加0.582 GB | 长期RAM平台未确立，继续定位 |

状态仅反映本页更新时已闭合证据。CPU测试、接口存在、动作请求被接受和历史单集成功不能替代本轮连续物理运行。

## 显式版本和记录模式

所有新版运行命令保留 `--project-version Project_release_v1`。省略版本仍运行旧 `Project_v1`，不自动迁移历史输出。

```bash
# 已实际执行的GUI启动与正常结束检查，非完整teacher装载
./labsim demo --project-version Project_release_v1 --sequence early_finish \
  --gui --record-mode eval \
  --output outputs/lab_cuvette_loading/Project_release_v1/gui_NEW

# 本轮已实际闭合的同进程三集验收
./labsim collect --project-version Project_release_v1 --headless --record-mode collect \
  --sequence teacher early_finish teacher \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_NEW
```

`--sequence`是明确的teacher/生命周期验收序列，不是零样本策略控制或任务宏。`early_finish`真实推进3秒后提前结束；中间失败标签不会被后续reset改写。常规teacher、GPT及RPC入口不带该参数，沿用独立launcher；其本轮实际验证范围另记。

`collect`和`eval`当前保留完整双相机H5、原生侧视/腕视/双视角录像，物理和接触日志采用lossless gzip，移除collector重复录像；`diagnostic`保留plain日志和额外collector录像。三种模式均保持在线物理、评分及安全采样，不把eval称为无图像轻量模式。细节见[生命周期说明](lifecycle.md)。

## 读取与数据资格

必须等待Isaac进程退出并确认完成标记后读取。运行未闭合、写入失败、异常中断及几何诊断不会因目录存在而进入正式训练索引。重复finish返回既有结果；完成资格、H5与索引共用finalization ID。

正常入口为 `./labsim dataset-check --path ... --sample-filter success|failure|all_valid --policy both --output ...`。多集索引默认相对外链，移动时保留整棵collection树；它不是单文件便携H5。仅在显式选择copy模式时复制完整多集数据。本轮三集H5已全量读取，42项底层ACT/DP读取检查通过；底层实际筛选success/failure/all_valid为2/1/3，未完成为0。正式`./labsim dataset-check`曾在clean122拒绝受控结束组；独立release reader于4a71635修复该白名单后，在干净checkout实际重跑三filter，ACT/DP的2/1/3均通过。原H5标签、旧v1.1 reader和物理/BC门槛不变；不能将底层42项误写为修复前正式入口通过。证据：[success](validation/official_dataset_check_clean_4a71635/success.json)、[failure](validation/official_dataset_check_clean_4a71635/failure.json)、[all_valid](validation/official_dataset_check_clean_4a71635/all_valid.json)。三集使用同一原生进程，初始q9与器皿记录一致；旧集动作请求均拒绝且零步执行。六条gzip流全量核对字节SHA、行数及EOF/CRC通过。第2集是明确的受控提前结束，不冒充模型任务失败。

## 外部策略与接口

真实π0.5使用现有LIBERO checkpoint，通过同一正式RPC获取观察、推理、执行有界动作、接收回执并正常结束。适配只做已声明的状态与动作空间转换，不增加器皿/目标座真值、不调用teacher。chunk未执行部分在拒绝、部分执行或终止后丢弃。模型等待时仿真暂停。本轮已真实执行69次推理、341动作、1021控制步、17.017秒，最后一个动作部分执行并由ROBOT_ENVIRONMENT_COLLISION安全停止。任务失败、记录有效；69次检查确认等待时物理暂停。环境在10个短reset资源探针后已正常关闭，原生视频现可读取；这些探针不算模型评测或任务失败，全量数据及9D实际动作、后继状态链和正常读取均已核查，见[闭合数据审计](validation/pi05_standard_01_env_closed/summary.json)。模型264-token提示词超200截断警告保留，没有为本轮调优。完整动作与相机语义见[外部策略契约](external_policy/contract.md)。

GPT既有能力保留，本轮不优化提示词，不新增付费调用。Project_v1_1 GPT08是稳定搬运后主动结束的有效失败，不能当作本轮π0.5验收或GPT装载成功。

π0.5源环境有1条真实模型episode和10条短reset资源探针。原始通用failure/all_valid可读11条有效短记录，但不代表11条模型失败。本轮模型评测使用[专用策展索引](validation/pi05_standard_01_env_closed/real_policy_evaluation_only_index.hdf5)及[成员清单](validation/pi05_standard_01_env_closed/curated_index_manifest.json)，只包括episode0000；筛选为0/1/1，原标签不修改。索引依赖原H5，不能单独下载当作完整轨迹。

## 发布与已知边界

固定资产revision为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)，冻结代码为 `4a716359376de0132cc83cba3e5c7d27c791069e`，[对应CPU CI](https://github.com/zez2001/LabSim/actions/runs/40491901758)已成功。实际物理核心素材使用122c4c0，保留其运行身份。终止CLI薄层73b1a9d和reader修复4a71635、后续文档发布提交与该物理核心实际执行提交分别记录，不把文档提交冒称已运行代码。

常规collect同口径完整episode从3,878,360,980 B降至2,327,380,401 B，减少1,550,980,579 B（39.9906%）；物理/接触日志减少约85.1%，H5图像与时间关系不删减。首teacher rollout从1129.265 s至1086.598 s，但第三集为1191.886 s，因此仅确认存储收益，不能归纳稳定提速。三集末RSS为8.338/8.518/8.920 GB，增加0.582 GB；这不是内存泄漏证明，也不证明长期资源平台已稳定。

实际交付native双视角视频为1280×480、30 fps；配置保留的main_resolution 1920×1080不能当作实际MP4分辨率。

菜单owner在USD卸载前关闭，真实短程GUI运行未复现旧`get_stage_state`异常；退出阶段SDK扩展的`ManipulatorFactory`回调错误仍存在，GUI与headless都曾观察到，数据与进程正常闭合。新版本不修改用户安装的扩展。五类受控终止已实际运行：主动结束、无进展上限、不可达预规划拒绝、服务超时注入和用户中断注入；后两者结果为null/invalid，不计任务失败。[145项闭合审计](validation/termination_cases_01_closed/summary.json)及[35项权威字段补充](validation/termination_cases_01_closed/authoritative_fields_addendum.json)均通过，15路MP4完整解码。原independent_score是pre-close pending快照并保留其阶段语义；最终权威资格字段一致，不回写历史快照。原生速度与差分差异、有效碰撞烹饪表示未完整读回及未真实校准的历史边界继续保留。

后续10个短reset资源探针中RSS约5.713→6.081 GB，FD332→334，采样VRAM为3627/3691 MiB；与三集结果范围分开，长程memory plateau仍未证实。

没有第二台机器的部署证据。本轮不训练、不采random、不修改器皿尺寸或原座、不建设checkpoint/resume；`finish`结束当前集，`reset`建立新集。
