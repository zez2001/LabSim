# 结果阅读包

每轮交付创建一个新目录，只收本轮改动与结果。保留旧包，不打包完整工程、环境、原始 H5 或检查点。完整工程通过 GitHub 分享，原始数据单独交接。

数字资产按用户 2026-10-27 的最新要求，只保留 `~/SLAI_Lab/labsim/results/final/` 一套交付，旧日期包已清理。当前 [交接汇报](../cell_assets/交接汇报.md) 列明 4 类限定机械操作、OpenFlexure 失败、剩余缺口及复现方法。HTML 内嵌 40 段视频，必要证据与来源集中保留。此项按用户要求仅本地整理，未提交、推送或创建 PR。

纯工程管理、文档或接口整理只放新的项目文档、相关源码与检查结果，不重复复制旧实验的大视频和报告。新实验需要时加入本轮 DOCX / Markdown、代表录像、结果表、配置及评分证据，保持报告和媒体的相对目录结构。

## 选择文件

当前默认[清单](package.json)是 [Project_v1_1 本轮结果清单](Project_v1_1_current/package.json)：8页DOCX及Markdown报告、完整teacher成功与释放近景、GPT座口滑移和最新未完成尝试、逐条结果与复现证据，约18MB。先读 [本轮说明](Project_v1_1_current/00_给Agent阅读说明.md)。

包内保持仓库相对层级，DOCX本地视频和图片链接可直接使用。旧 [Project_v1结果清单](Project_v1_current/package.json) 及其他历史包保留。

纯项目交接的旧配置仍保留在 [project_handoff/package.json](project_handoff/package.json)，历史实验通过固定提交的 GitHub 链接引用。

清单支持整个目录和独立文件，可组合使用：

```json
{
  "schema": "labsim.agent_results_package.v1",
  "repository_url": "https://github.com/zez2001/LabSim",
  "readme": "docs/agent_handoff/project_handoff/00_交接阅读说明.md",
  "directories": [
    {"source": "docs/development", "destination": "开发接入"}
  ],
  "files": [
    {"source": "README.md", "destination": "项目README.md"}
  ]
}
```

source必须指向仓库内真实内容，destination必须在包内。脚本拒绝越界、symlink、重复或冲突目标、未下载的 LFS 指针和覆盖已有输出。旧的仅含directories的清单继续兼容。

Markdown里已选中的文件链接会改为包内相对链接；未复制的仓库文件链接会固定到本次提交的GitHub路径。DOCX相对媒体链接须在作者阶段做好，并把相应媒体目录一并纳入。源码路径与大数据路径若只用于追溯，必须明确其并未复制到包内。

## 生成与检查

先验证改动、提交推送并核对远端SHA，再在工程根目录运行：

```bash
python3 scripts/package_agent_results.py --manifest docs/agent_handoff/package.json --output /home/wujing/Desktop/LabSim_Project_v1_1_本轮结果阅读包_NEW
```

输出目录必须尚不存在。实验资料通常控制在20MiB内；纯工程整理应更小。不要为接近体积预算而复制不相关历史媒体。

包根的文件清单.json记录实际提交、分支、源文件SHA、转换及复制后SHA；SHA256SUMS.txt用于传输后的逐文件检查：

```bash
cd /path/to/reading-package
sha256sum --check SHA256SUMS.txt
```

交付前检查总大小、包内相对链接、媒体实体、配置和报告引用；不把内部预览包或未推送工作树标成最终交付。不要预填未来提交SHA，也不把旧实验报告描述为本轮新运行。

## 实验数据范围

数字资产的 IKA、DIYNAFLUOR、Flex／MagSep 与失败对照统一见 `~/SLAI_Lab/labsim/results/final/evidence/`；这次覆盖旧包的清理要求仅适用于该数字资产交付。

结果包不建立新的数据平台，不修改原始标签。完整任务、几何预检、初始化、服务异常、人工中断、短预算接口诊断和实际受控失败须区分。

Size_v1的最终40集证据保存在[正式审计目录](../lab_cuvette_loading/Size_v1/data/final40_actual/README.md)。刷新其小型配置快照应使用真实的最终审计和汇总，不能把计划配额写成已完成。需要重新制作包含视频的实验包时，从历史清单选择必要目录，并指向实际存在的results_20261022，不覆盖旧包。
