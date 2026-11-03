# 恢复历史 gpt_debug04 并独立复测

本目录保存历史 `gpt_debug_04` 的完整策略身份、只读量化和当前标准场景的一次独立复测。`debug04` 是历史运行编号；实际策略是 **v4 通用工具、context4、640/high 双图、gpt-6-astra / Cubence**，不是 P4，也不是此前 P9。

## 结果与入口

历史原集确认抓持、离架、持物横移及进入预插入区域，最终为 `GRASP_SLIP`，没有完成装载。当前复测确认抓持、离架和持物横移，最终为 `BLOCKED / POLICY_FINISH_REQUEST`，完整成功 **0/1**。模型实际张开了夹爪；器皿停在入口局部结构上，底部距规定承托面约 26.998 mm，未达到合法装载、释放和撤离条件。末尾静置不能替代撤离后稳定检查。

- [本轮完整量化报告](RESULTS.md)：历史与新集分别统计，阶段时间、连续量、失败解释及费用。
- [DOCX 报告](LabSim_GPT_debug04_恢复与基线评测报告.docx)：含实际轨迹图、关键画面及两组独立结果。
- [策略身份](identity.md)与[机器身份清单](identity.json)：原配置、prompt、工具、视觉、上下文、信息边界和 SHA256。
- [环境对照](environment_comparison.md)：历史与当前资产、执行器、相机、物理和兼容桥。
- [独立恢复源码](../../../policy/backends/gpt_debug04_v1/)与[冻结协议](../../../config/lab_cuvette_loading/Gpt_debug04_v1/protocol_template.json)。
- [正常 ACT/DP reader 验证](validation/official_reader_summary.json)：真实失败 batch 可读，原 H5 和任务标签不变。
- [结果阅读包说明](../../agent_handoff/Gpt_debug04_v1_current/00_给Agent阅读说明.md)：完整历史、新集视频及离线 Progress 页面随桌面阅读包提供。

## 恢复范围

历史提交 `63410bf9258ba2f9bd0af4d517194523fca6617c` 的三份策略模块逐字保存于独立 vendor 命名空间。原 prompt、工具 schema、双图编码、最近两回合文本上下文、动作限制和主动 finish 行为保持。没有加入动态器皿真值、Progress、Teacher 路径、抓取宏或 P9 扩展。

当前环境为 `Project_release_v1 / standard`，Progress v1.2 开启，沿用 10×10×67.5 mm 器皿、原内部 A 座、240 Hz 物理与 60 Hz 控制。物理配置、成功条件及数据资格保持基线。共享启动器只增加显式客户端和策略执行器注入入口，默认路径兼容原调用。

## 运行与预算

先在已准备 Isaac Sim 的 Python 环境执行只读检查：

```bash
python -m demos.lab_cuvette_gpt_debug04_v1.run --check-only
```

此命令不加载 Isaac、不读取凭据、不创建账本、不调用模型。付费执行要求干净的已提交源码、完整 HF 资产和独立明确授权。启动器使用的实际版本、协议、源码哈希、授权及输出均写入运行清单。

```bash
python -m demos.lab_cuvette_gpt_debug04_v1.run \
  --authorization /absolute/path/to/approved_authorization.json \
  --ledger /absolute/path/to/authorized_cumulative_budget.json \
  --trial-id debug04_01 \
  --output /absolute/path/to/new_environment_output \
  --headless
```

以上是接口格式。**本次 `debug04_01` 授权已使用，不能再次消费或换目录重跑。** 新授权须绑定实际账本路径、原账本哈希、协议哈希及集数；不得复制授权绕过限制。凭据使用默认私有位置或 `--credential-file`，不写入仓库。未来迁移机器时应重新生成显式路径配置和对应协议指纹，不改写已执行协议。

本次用户授权新增 USD20、最多480次网络请求、正式1集。实际新增42次、估算 USD3.445010，策略主动 finish，未因预算截断。旧377次／USD29.267746原账本完整不变，新累计账本保留全部旧费用。剩余金额不构成新增集数授权；计划中的其余9集为未授权、未启动，不进入分母。

## 正常数据入口

进程完全退出、记录闭合后，用发布版原索引与 reader：

```bash
python -m demos.lab_cuvette_project_release_v1.dataset_index \
  /absolute/path/to/environment --purpose policy_evaluation \
  --output /absolute/path/to/index/policy_evaluation.hdf5
./labsim dataset-check --index /absolute/path/to/index/policy_evaluation.hdf5 \
  --sample-filter failure --policy both \
  --output /absolute/path/to/new_reader_result.json
```

本次索引为 success0／failure1／all_valid1，6060条 transition 时间对齐。ACT、DP均实际读取 batch；`task_success=false`、`record_valid=true`、`success_bc_eligible=false` 保持原样。此数据用于失败分析，不进入默认成功 BC 数据集。阅读包提供视频和分析证据；完整约1.50 GB原始H5保存在本机独立输出目录，没有塞入精简阅读包。

## 版本与统计边界

历史原运行提交为 `63410bf`；本次实际执行提交为 **`801a3f704298faf00cc31b55d572e5e0ff4bb4b6`**。报告及分析工具发布提交另见阅读包的 `publication.json`，不冒充运行时版本。

本组只有一次新复测，不能据此估计稳定成功率或归因历史差异。此前 [P9 与 π0.5 评测](../Policy_eval_v1/README.md)独立保留，未重跑、未并入本组分母。原生烹饪碰撞重叠不可完整读取等质量告警随原记录保留；当前结果是固定仿真场景中的策略能力，不是实物校准结论。
