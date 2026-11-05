# 部署与交付边界

本页描述可迁移的部署和交付方式。当前任务、分支及发布权限以[AGENTS](AGENTS.md)和用户本次授权为准；历史日期分支和 PR 状态见[原交付记录](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/DELIVERY.md)，不作为当前发布入口。

## 工作区与运行环境

使用一个完整实验工程，例如 `/path/to/LabSim`；资产缓存可放 `/path/to/asset-cache`，运行结果放工程下 `outputs/<task>/<version>/<new-run>` 或 `results/<new-run>`。个人安装记录和安装包放本地 `local_setup/`。这些是角色示例，无需复刻其他协作者的 home、桌面或目录名。

运行基线为 Linux、Python 3.11、Isaac Sim 5.1.0 和兼容 NVIDIA GPU/驱动；历史物理验证使用 RTX 4090，不代表所有硬件组合均已验收。通过 `LABSIM_PYTHON=/path/to/installed/isaac-python` 选择解释器；具体准备步骤见[ONBOARDING](docs/development/ONBOARDING.md#准备环境与资产)。同一 GPU 顺序运行 Isaac 进程，新机器依次验证 doctor、完整 Teacher、进程退出、数据闭合和正常 reader，另记录实际硬件及版本。

## 资产与数据获取

- 比色皿发布版按[资产锁文件](config/lab_cuvette_loading/Project_v1/assets.lock.json)恢复，HF revision 为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)。这是显式白名单，不能推定覆盖所有历史场景或 CAD。
- 单细胞源资产位于 [PercyM/labsim-cell-assets](https://huggingface.co/datasets/PercyM/labsim-cell-assets)，初始源包固定 revision 为 `f6b0f9f2dbe5046c0833fb099121e5a551d208f7`。7 个注册条目、307 个源文件的来源、许可、更新 revision 与下载方法见[发布与调用指南](docs/cell_assets/HuggingFace上传指南.md)。它不等于完整动态 unit 场景包，新派生场景、权重和录像的发布范围须逐项核对。
- 单细胞镜像解压到完整工程的 `local_assets/`，使用 `fetch_asset(..., offline=True)`；也可通过 `LABSIM_ASSET_CACHE` 指定相应缓存。不同资产 API 的缓存结构以各自说明为准。
- HDF5 外链索引不是独立样本。移交必须携带其来源 H5 和相对树，或另生成有来源哈希的 copy 派生物，见[数据移交](docs/lab_cuvette_loading/Project_release_v1/data_usage.md)。不得改写原历史索引冒充便携数据。

## 保存与发布

Git 保存代码、配置、协议、当前文档、来源清单及运行/CPU 所需小型 fixture。版本化大型数字资产与正式数据集使用 HF，记录 revision、许可、文件大小及哈希。本地输出/结果/缓存留在忽略目录；获授权的里程碑、历史结果包及代表视频使用 GitHub Release，记录固定源码与资产/数据版本。历史原始小证据和已跟踪资产不因这套新文件归属原则而自动迁出 Git。

HF 源资产镜像不包含全部 Franka、房间和旧场景资源。代码交付副本省略模型/媒体，不代表应从上游 Git 删除这些文件；`assets/README.md`、运行 registry/sidecar、锁文件及 `docs/` 中的运行门禁、动态工具和测试输入必须保留。迁移前逐项核对消费者、来源和依赖闭包。

发布只有在上传完成并回读核对文件 SHA256 后才记为已发布。离线检查、LFS 指针、本地包或待上传清单均不能证明远端实体可用；未发布/缺失项明确列出，不静默下载或补造。历史结果和归档入口见[统一结果索引](docs/history/RESULTS.md)。

## 可选代码快照

仅在当前任务明确需要代码副本、并授权其输出与旧受管理快照处理时执行：

```bash
python3 -B scripts/export_code_snapshot.py
```

现有导出器在完整工程同级 `codex/` 下生成兼容命名的日期目录；该目录名不是开发分支约定。它包含已保存工作树的源码、配置、测试及 Markdown，可能含未提交改动；省略 Git 历史、模型、媒体、环境、实验输出和部分非 Markdown 的运行依赖，因此不能作为完整可运行仓库。`snapshot.json` 记录来源、HEAD、工作树状态及逐文件哈希，不是已提交/已发布证明。

导出器会替换经哈希核验未被手工修改的旧受管理快照，故不能把“生成代码快照”当作保留历史结果包的方式。不要编辑生成副本或在那里运行实验；需要保留版本的正式代码使用 Git，阅读包规则见[结果阅读包](docs/agent_handoff/README.md)。
