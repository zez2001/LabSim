# 代码交付说明

本文件同时进入自动生成的 `codex/labsim_junjie_yao_YYYYMMDD/` 交付副本。副本包含当前已保存的源码、配置、测试、依赖说明和中文 Markdown，包含尚未提交的工作树改动；不带 Git 历史、不自动提交或上传。建议后续功能分支名与副本相同。

当前 GitHub 交付：[PR #1](https://github.com/zez2001/LabSim/pull/1)，分支 `codex/labsim_junjie_yao_20261027` → `codex/labsim`，未合并。

## 下载数字资产

- HF 仓库：<https://huggingface.co/datasets/PercyM/labsim-cell-assets>（Private，需要访问权限）。
- 完整仪器源包：<https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/f6b0f9f2dbe5046c0833fb099121e5a551d208f7/assets/LabSim-digital-assets.zip?download=true>。
- 固定版本：`f6b0f9f2dbe5046c0833fb099121e5a551d208f7`，7 个注册条目、307 个源文件；许可与能力边界见 [发布与调用指南](docs/cell_assets/HuggingFace上传指南.md)。
- 在可运行的 LabSim 工程根目录解压到 `local_assets/` 后，使用 `fetch_asset(..., offline=True)`，再在 Isaac Sim 5.1 内转换和加载。也可通过 `LABSIM_ASSET_CACHE` 指向完整实验工程的缓存。
- 视频、HTML 和证据可从同一仓库的 `videos/`、`showcase/`、`evidence/` 获取。

## 原工程基础依赖

本交付副本保留 [`assets/README.md`](assets/README.md) 作为资产获取入口，不包含其中的大型模型，也不包含 `images/`、录像、图像、环境与实验输出。HF 仪器镜像不包含原工程全部 Franka、房间和场景资源。接手者应在保留原有基础资源的 LabSim 基线上集成代码变更；副本里省略的模型/媒体不代表应从上游 Git 仓库删除这些文件。完整本地实验工程中的原始资源均保留。

运行版本：Python 3.11、Isaac Sim 5.1；依赖见 `requirements.txt` 和 [实验入口说明](demos/cell_assets/README.md)。当前固定布局的仿真结果不等于真机校准。

## 更新方式

只在工作区 `labsim/` 中修改代码与做实验。验证并更新交接说明后运行：

```bash
python scripts/export_code_snapshot.py
```

自动生成同级 `codex/labsim_junjie_yao_YYYYMMDD/`，不把源工程、资产或运行环境复制成第二份。`snapshot.json` 记录源分支、HEAD、包含未提交改动的说明和逐文件哈希。它不是一次 Git 提交证明。不要直接编辑生成副本；需修订时回到完整工程再导出。
