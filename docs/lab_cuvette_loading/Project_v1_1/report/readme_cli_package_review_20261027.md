# README、版本入口与精简阅读包只读审查

审查日期：2026-10-27。本文只给编辑建议；没有改 README、usage、CLI、运行配置或打包脚本。审查时 HEAD 为 `9750a37e09a377e1f86fee5a8b52d2bebf3282eb`，含正在开发的新版本；这不是最终交付版本声明。逐命令输出、源文件 SHA 与源视频检查见 [JSON 记录](readme_cli_package_review_20261027.json)。

## 主页最小修改建议

保留当前“能力—第一次运行—示范/评测/采集—GPT—正常读取—证据与限制”的项目使用结构，不在主页加入诊断迭代流水账。建议只改五处：

1. 开头把“当前入口”明确为“默认稳定入口 `lab_cuvette_loading / Project_v1 / standard`”，随后加一句“独立开发版本 Project_v1_1 的调用方式见新版说明，完整物理与模型回归尚待闭合”。保留已有 Project_v1 teacher 代表录像，标清历史版本，不把它变成新版代表。
2. 在第一次运行示例后加一个版本选择短段和新版 usage 链接。示例保留旧版命令，再给显式 `--project-version Project_v1_1` 的 `--dry-run`；无需把所有旧命令改写为新版。
3. GPT 预算段加一句：Project_v1_1 延续 `outputs/lab_cuvette_loading/Project_v1/cubence_budget.json` 的既有请求及费用占用，先导、重试和正式运行继续共用，不能换空 ledger。继续保留估算 `$30 / 1500` 上限及“估算非账单”的现有说明。未产生新版正式结果前，不在主页添加新版 GPT 成功率。
4. 正常 reader 段加一句：`dataset-check` 按 H5 `scene_version` 自动选择独立版本 reader；合格成功、有效任务失败和控制诊断有不同资格，`control_diagnostic` 不进入成功 BC。链接新版 usage 的正常 ACT/DP 指引即可，不复制数据契约全文。
5. “验证证据与限制”中把当前“本轮同机干净 checkout”“新入口”“本轮发布”等指代明确为 **Project_v1**。已有 5/5 teacher、GPT 0 次完整成功等数字继续归属旧版本；新版状态只保留“待完整回归”的一句与文档链接。

可直接采用的新增短段（放在第一次运行的输出目录说明之后）：

~~~markdown
省略版本时继续运行 Project_v1。Project_v1_1 是独立版本，必须显式选择：

```bash
./labsim demo --project-version Project_v1_1 --backend teacher \\
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_preview_NEW --dry-run
```

新版的确定性诊断、共享预算、相机/控制版本和正常读取方式见
[Project_v1_1 调用说明](docs/lab_cuvette_loading/Project_v1_1/usage.md)。
完整物理与模型回归以该版本实际保存的结果为准。
~~~

示例是启动参数预览，不宣称 teacher 新版完整运行已通过。

## usage 与真实入口的对应关系

`demo/eval/collect/serve --project-version Project_v1_1` 实际均路由到 `demos.lab_cuvette_project_v1_1.run` 和新版 `standard.yaml`。默认版本仍为 Project_v1；旧 Size_v1 `collect --phase` 不允许混用新版。GUI 为未加 `--headless` 时的默认行为，usage 的 teacher demo 例子有效。

确定性诊断只有直接模块入口支持；`./labsim demo --backend diagnostic` 当前会被 CLI 拒绝。usage 采用直接模块是正确的。可在诊断段把解释器变量加引号，并明确从仓库根目录执行：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.run \
  --backend diagnostic --probe free-space-checked --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/free_checked_NEW
```

实际支持 `fixed-replay/free-space/free-space-checked/pose-hold/fine-preinsert/grasp-transport`。直接模块没有 `--dry-run`，只可先查 `--help`；不能在文档中让读者为预览诊断命令而启动物理运行。`free-space-checked` 是新的三个 reset 诊断；旧 `free-space` 的结果与覆盖范围不要混称。

建议在 usage 已有“新配置”段补三个精确字段，不新增实验数字：

- `config/lab_cuvette_loading/Project_v1_1/standard.yaml` 的 `project.camera_version=Project_v1_1.wrist.v2`；具体固定挂点在 `cameras.wrist_camera`。
- 同文件 `project.executor_version=Project_v1_1.continuous_fk_executor.v1`，边界参数在 `executor`。
- 同文件 `robot_tracking.version=Project_v1_1.robot_tracking.v1`，启用状态与有界补偿参数在 `robot_tracking`。

这三个字段说明当前配置选择，不代表最终相机效果、完整装载、真实精度或最终 teacher/GPT 回归已经验收。GPT 真正发送的输入与 teacher 的未发送预览应继续分开记录。

正常 `dataset-check` 不需要 `--project-version`；实际按 H5 scene_version 决定 Dataset。usage 的未来 teacher 样例路径是使用示例，不是本机已存在结果。审查时只对已闭合 fine02 路径执行了 `dataset-check --dry-run` 检查路径解析；它没有读取 batch，也不能因该命令成功就把诊断纳入 success。正常 reader 的真实验证另见 [CPU 回归](../validation/cpu_regression_20261027/README.md)。

## 本次实际轻量检查

共 9 条退出码均为 0：默认 demo dry-run；新版 demo/eval5/gpt/collect/serve dry-run；闭合 H5 路径的 reader dry-run；新版模块 help；打包脚本 help。所有 `labsim_readonly_review*` 预览输出仍不存在。未启动 Isaac、未调用 API、未读活跃输出、未构建阅读包。

## 精简阅读包可用命令与条件

现有脚本入口可用，支持显式文件 allowlist、目录和交叉链接重定位：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/package_agent_results.py \
  --manifest docs/agent_handoff/Project_v1_1_current/package.json \
  --output /home/wujing/Desktop/LabSim_Project_v1_1_本轮结果阅读包_NEW
```

**上面的新版 manifest 尚未建立，因此这是最终准备好之后的命令格式，当前不可作为已可打包结果。** 默认 `docs/agent_handoff/package.json` 仍指向旧 Project_v1，必须显式给新版清单；不要直接执行默认命令。先完成真正的最终证据、DOCX 全页 QA、提交推送和远端 SHA/CI 校验，再生成不存在的新桌面目录。脚本记录当前 HEAD 和工作树状态，但不替调用者强制执行 clean/pushed/remote-CI 检查。

脚本当前已保证：源文件在仓库内真实存在、不是 symlink、不是 LFS 指针；拒绝选择越界与目标冲突、拒绝覆盖旧包；复制前后 SHA 一致；每个包内 Markdown 相对链接在包内存在；最后写 `文件清单.json` 和 `SHA256SUMS.txt`。传输后在包内运行 `sha256sum --check SHA256SUMS.txt`。

最终链接与视频还需以下人工/独立校验：

- 首读说明只替换 metadata 占位符，不做通用 Markdown 重定位；作者应直接写按包根目录可用的相对链接。DOCX 链接完全不重写，应保留 `Project_v1_1/report` 与同级 `media/diagnostics/validation` 的相对布局。
- 普通 Markdown 的绝对本机路径若能映射到选择文件，可能被改相对；超出仓库的绝对本机路径会报错。`file://` 这类带 scheme 链接会被保留，且不验证目标；交付文档不应使用。带 `<...>` 的 Markdown 目标及 HTML 链接不是当前简单正则的完整支持范围，最终文档宜使用普通、百分号编码的相对 Markdown 目标并逐个验。
- 未复制的本地文件会生成当前 HEAD 的 GitHub URL；脚本只检查本地存在，**不检查该目标在 HEAD 已被追踪**。忽略输出、未提交证据、历史外盘路径不可因此伪装成可访问远程链接。历史背景使用已经核实的固定提交链接。
- 外部 HTTPS URL 的联网可达性、DOCX 内关系、视频解码和每个视频的同一 episode 连续性均不由打包脚本验证。报告应引用精选当前媒体的实体，附来源、SHA、帧数/时长及完整解码/视觉检查记录。

## 当前闭合源视频存在性

已对 grasp_transport_01、grasp_transport_02、fine_preinsert_02 的 `dual_view.mp4`、side/wrist、正常 collector 视频共 12 个文件检查：均存在、非 symlink、非 LFS 指针，ffprobe 均可读取编码/尺寸/帧数/时长。本次仅检查实体与容器元数据，未声称重新全解码。

三个 dual-view 源分别为 5,634,588 B / 30.034 s、6,107,954 B / 33.267 s、15,716,771 B / 87.334 s。源视频均在被忽略的 outputs 中；当前尚无 `docs/lab_cuvette_loading/Project_v1_1/media` 或最终新版 manifest。它们不是已发布链接。最终按实际需要精选同次连续 H264 媒体、核对时标；不要把三轮所有视频直接塞进小包。完整原始视频继续由来源 SHA 追溯，H5/JSONL gzip/环境/旧实验媒体不进入当前-only 包。
