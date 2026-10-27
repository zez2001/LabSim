# LabSim 文档与内部使用优化反馈

日期：2026-10-28。推荐版本：`Project_release_v1`。开发分支：`codex/labsim`。

普通Teacher完整任务已实际成功，正式ACT和DP入口均读出成功batch。当前指南已统一到完整任务与标准采集；数据用途、历史兼容、移交依赖及图像/文本输入得到独立定义。场景、器皿/原座、质量摩擦、控制器、动作转换数值及成功判据沿用发布基线。

## 当前使用文档与推荐命令

从[主页](../../../../README.md)开始，组内操作按[ONBOARDING](../../../development/ONBOARDING.md)的“准备环境—完整任务—采集—读取—策略接入”执行。中文版与英文版命令一致；中文导航简化为单一入口。

完整命令见[commands.sh](commands.sh)。第一条demo使用普通完整Teacher，第一条collect采集标准完整示范。三秒安装检查和混合生命周期序列移到开发验收。`--project-version current`解析为真实`Project_release_v1`；未指定版本继续兼容`Project_v1`。

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration --output outputs/demo_NEW

export LABSIM_RUN=outputs/collect_NEW
./labsim collect --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode collect --record-purpose demonstration --output "$LABSIM_RUN"
# 等待进程关闭。
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose demonstration --output "$LABSIM_RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/index/demonstrations.hdf5" \
  --sample-filter success --policy both --output "$LABSIM_RUN/read_success.json"

./labsim serve --project-version Project_release_v1 --headless --port 8097 \
  --record-mode eval --record-purpose policy_evaluation --output outputs/rpc_NEW
```

启动摘要及JSON保存真实版本、任务与场景、后端、资产、源/解析配置及场景指纹、模式、用途和目录。版本技术参考、数据使用、策略契约各自管理规格；原发布说明按原字节归档，历史README增加当前入口。

## 本次完整Teacher回归

实际执行提交：`5c6b6422f9ba6fc16ac7b4374799c5ed7e426e47`；干净checkout、普通`demo`路由、GUI、`record_mode=collect`、`record_purpose=demonstration`，没有使用`--sequence`。

| 项目 | 实际结果 |
|---|---|
| 完整独立评分 | task_success=true，record_valid=true，record_integrity_valid=true，success_bc_eligible=true |
| 阶段 | 抓取、清槽、搬运、原A座插入、承托交接、松爪、脱指、撤离、稳定实际完成 |
| 稳定观察 | 3.0秒，721个物理样本 |
| 时间 | 125.6667秒仿真；父进程观测启动至退出1185.067秒 |
| 数据 | 7539条transition，8维训练动作、9维执行命令 |
| H5 | 1,944,646,901 bytes；40个独立数据对象全量读取；SHA读取前后相同 |
| ACT | 图像batch [3,3,256,256]，动作[3,16,8]，全部有限 |
| DP | 图像batch [3,3,3,256,256]，动作[3,16,8]，全部有限 |
| 记录身份 | Project_release_v1 / cuvette_xy_1000 / A1 / candidate_far_hinge / demonstration |
| 视频 | 三路全部解码通过；原始双视角1280×480、30fps、125.700秒 |

[原始连续双视角录像](media/teacher_full.mp4) · [场景](media/scene.png) · [插入腕视](media/insert_wrist.png) · [独立结果](teacher_closed/result.json) · [实际reader](teacher_closed/read_success.json) · [完整闭合摘要](teacher_closed/summary.json)。

全量时间数组：后继步号增加1，后继时间增量1/60秒，next_state时间与下一行观察一致；相机时间单调，扣除引擎原点后与观察的最大差为6.553微秒。该数值是时间戳检查，像素与物理姿态同步另按其明确范围解释，见[时间审计](teacher_closed/transition_clock.json)。

保留物理质量告警：`NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT`、`NATIVE_TARGET_OVERLAP_UNAVAILABLE`。工程输入几何和记录状态判据通过；有效烹饪几何及真实校准沿用原验证范围。退出时保留已知SDK扩展回调日志，应用完整cleanup返回，原生及launcher PID均已消失。

## 用途筛选和历史数据

新字段`record_purpose`由调用意图显式声明，保存至启动身份、运行清单、H5、嵌入元数据、结果、完成标记和发布索引。四类为`demonstration`、`policy_evaluation`、`lifecycle_diagnostic`、`resource_probe`；不按成功、时长或动作数量推断。

用途决定集合；success/failure/all_valid继续采用原资格语义。索引CLI默认policy_evaluation，示范显式demonstration，诊断显式all-completed。兼容Python API默认all-completed；新调用应显式声明。

历史sidecar绑定episode UUID、相对源H5路径与完整SHA，未知用途需显式成员选择。复用旧π0.5清单得到正式策略1条、诊断11条、资源探针10条；生命周期三集保留资格2/1/3。14个历史H5及原标签SHA前后相同。新普通Teacher示范索引为success/failure/all_valid=1/0/1，正式ACT/DP读取成功。详细[用途验收](data_usage/README.md)和[新示范索引回执](teacher_closed/demonstrations.index.json)。

## 输入事实与本地审计

| 层 | 实际表示与转换 |
|---|---|
| 原生/公开观察 | 每路480×640×3 HWC RGB uint8 |
| H5/训练reader | OpenCV INTER_AREA拉伸至256×256，CHW uint8；reader转float32 0–1 |
| π0.5线上输入 | [1,480,640,3] NHWC uint8；客户端只增加batch |
| checkpoint processor | PIL BILINEAR到224×168，上下各28像素黑边；模型张量[1,3,224,224]、float32 −1…1 |

69份历史真实NPZ与原推理回执逐数组SHA一致；两路H5首帧对应其256×256记录分支。实际部署PaliGemma SentencePiece tokenizer、max_token_len=200、discrete_state_input=false。首末文本同哈希，264 tokens保留200、截断64，截断发生在TCP四元数中。完整IDs、mask、decode、tokenizer/processor源码与版本见[输入审计](../../Project_release_v1/internal_use/20261028/input_audit/README.md)。

历史内部处理张量由同一部署源码离线重建；新增服务包装今后直接记录实际processor输出，只调用原processor一次且返回同一结果对象。本次没有加载权重或开展新policy rollout，没有修改提示词、图像或动作转换数值。

## 数据移交与验证范围

relative-links需携带索引和来源H5并保持相对目录。transfer检查列出解析路径、存在性、身份、SHA及需要携带的文件，缺失退出2并指出具体项。copy为自包含文件，保留相机别名hardlink。

10项新增小型有效H5测试覆盖整树移动后读取、缺源报告、copy独立移动、hardlink、成员和writer保护；历史集成54项通过。新实际示范索引[完整依赖校验](teacher_closed/dependencies.json)通过。活动writer保护继续用于同机关闭后处理；跨机/PID复用需要关闭凭据和文件检查，完整离线导入机制单列后续。

新增最短必要native采集检查：同一进程完成两次3秒early_finish，episode身份唯一，旧动作拒绝且零步执行；两集record_purpose=lifecycle_diagnostic。诊断索引2条可由正式ACT/DP读取，默认正式策略集合纳入0条。见[双reset闭合](reset_closed/summary.json)。

CPU工作流全部904项通过；当前指南138个本地链接/锚点和19条真实CLI路由通过，中英文命令一致。doctor退出0且errors为空。证据：[CPU](cpu_contracts.xml)、[文档](docs_check.json)、[doctor](doctor_current.json)、[保护清单](preservation.json)。

## 版本与后续事项

运行提交、后续代码/文档发布提交分别记录。最终发布SHA、远端核对及对应CI以阅读包publication.json和文件清单为准；HF revision继续为`bb880f098180c291f6f65995f969d48047207067`。

内部使用影响排序：

1. π0.5任务文本截断：已有预检及有效输入审计，后续精简使用独立命名输入配置。
2. 大批次RSS增长：当前按有限分组正常关闭并监测，长程内存另行定位。
3. SDK退出回调：保留日志与完整关闭凭据，SDK升级另行管理。
4. 跨机PID/离线导入：保留活动writer保护，完整身份机制后续实现。
5. 真实质量摩擦、动力学及有效碰撞几何校准继续独立推进。

源码与完整配置从GitHub获得。本次阅读包只含新报告、指南、必要证据与原始连续视频；完整H5约1.94GB，按数据指南单独移交，不包含环境、资产大包或模型权重。
