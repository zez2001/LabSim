# LabSim 环境发布：本轮技术反馈包

生成时间：{{GENERATED_AT}}；分支：`{{BRANCH}}`；交付源码提交：`{{SOURCE_COMMIT}}`。

这是本轮 `Project_release_v1` 的结果核查材料，完整工程在 [固定提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。包内源码是便于审阅的变更子集，不能把本包当作完整安装包。原始大数据、Isaac 环境、策略权重和凭据均未打包。

**当前清单是准备稿，不是最终验收通过证明。** 同进程三集、真实 π0.5 连续交互、终止类别覆盖、优化收益及最终媒体，只能以进程关闭后的实际证据为准。最终打包前须核对 [待补项](docs/agent_handoff/Project_release_v1_current/package_readiness.json)，更新本段及清单；不得把计划中的 2/1/3 筛选数量或 400 个动作写成已完成。

建议阅读顺序：

1. [环境验收报告](docs/lab_cuvette_loading/Project_release_v1/release_acceptance.md)：本轮范围、实际结果、准确命令、修复与遗留项。
2. [发布版入口](docs/lab_cuvette_loading/Project_release_v1/README.md)、[生命周期及事务闭合](docs/lab_cuvette_loading/Project_release_v1/lifecycle.md)、[外部策略契约](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。
3. `docs/lab_cuvette_loading/Project_release_v1/validation/`：逐条 JSON/CSV、CPU 注入与实际物理运行分开；baseline 与 GUI 的闭合、读取及来源核对。
4. `outputs/lab_cuvette_loading/Project_release_v1/`：已经关闭的本轮运行所选原始小型结果、评分、reset、配置、结束标记和进程退出证明。大数据并未复制。
5. `config/`、`demos/lab_cuvette_project_release_v1/`、`tasks/`、`data_collectors/`、`policy/`、`policy_backends/`、`scripts/`、`tests/`：最终选入的发布配置、必要源码和验证代码。
6. `docs/lab_cuvette_loading/Project_release_v1/meeting_source/`：汇报文档/媒体制作来源及实际 QA；preview 字样只表示初版，不冒充最终稿。

物理任务仍为固定 standard：10×10×67.5 mm 尺寸假设器皿、20 g 假设质量、原 A 座 `candidate_far_hinge`、单台仪器和完整白色 6×6 架。不改变原座、不采 random、不开展训练、不增加付费 GPT 调用。真实校准未完成，模型任务成功与环境正确执行分别判定。

## 文件范围、原始数据与读取

[大数据出处清单](docs/agent_handoff/Project_release_v1_current/external_data_sources.json)从已关闭审计的逐文件清单提取真实路径、大小和 SHA256，**不是这些数据的下载服务**。本机路径仅为来源；接收者需向项目所有者索取相应完整 collection 目录，或在固定代码与资产版本上重新运行。固定 HF revision 提供场景资产，不代表提供本轮全部原始轨迹。

所有 `.h5` / `.hdf5` 都不在本技术包内，包括小型 relative-link 索引。包内 `readonly_episode_index.index.json` / `index_build_receipt.json` 记录实际索引构建结果和筛选依据；其 `index` 与 `source` 字段指向原机器上的数据。仅复制该 JSON 不能读取训练 batch，也不能声称是自包含数据。拿到完整来源树后，可在完整仓库中按下列形式重建新索引（输出不得已存在）：

```bash
python -m demos.lab_cuvette_project_release_v1.dataset_index /path/to/closed_collection \
  --output /path/to/NEW_release_index.hdf5 --mode relative-links
./labsim dataset-check --path /path/to/NEW_release_index.hdf5 \
  --sample-filter all_valid --policy both --output /path/to/NEW_reader_receipt.json
```

`relative-links` 必须将索引与所有来源 H5 一起移动；需单文件自包含时显式使用 `--mode copy`，这会复制完整大数据。`success`、`failure` 和 `all_valid` 读取结果以各次实际验收文件为准。不要仅因 H5 可打开就判定任务成功或记录资格合格。

报告中的未复制仓库链接由打包脚本转换到固定 GitHub 提交。配置里的本机环境路径、原始回执路径及上面读取命令中的占位路径均为追溯或用法，不是包内可执行资产。

## 传输核对

`文件清单.json` 记录实际交付提交、每个源文件/复制件 SHA256、大小及 Markdown 链接转换。传输后在本目录运行：

```bash
sha256sum --check SHA256SUMS.txt
```

本技术包与组会包相互独立。组会 ZIP 仅含一个 DOCX 和 1–2 个实际连续运行视频；视频若出现在技术包中，须由最终媒体清单说明真实来源、运行提交、结果和原样复制 hash。当前清单不预填尚未关闭的媒体路径。
