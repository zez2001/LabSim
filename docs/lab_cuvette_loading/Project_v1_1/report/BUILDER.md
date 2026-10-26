# 新版报告生成器准备说明

此目录的 `generate_report.py` 是独立 Project_v1_1 生成器。它没有内置旧版 teacher、GPT、资产发布或费用结果，不导入旧版 report builder。`report_inputs.example.json` 只是 `finalized=false` 的七页结构模板，其中 cohort 的零计数也是占位，不是实际运行统计。

本轮只准备脚本、输入模板和 CPU 验证测试源码；没有运行生成器、没有生成 DOCX、没有执行 artifact marker，也没有渲染。实际正文以最终证据填写后，再进行 authoring 与全页 QA。

## 设计与输入

采用中文技术交接报告结构，正文结论先行。Letter 纵向，正文 11 pt、约 15 pt 行距；Title/各级 heading 为黑色、无下划线、无装饰线。表格 9.5 pt、主动列宽、浅灰边框、足够内边距和重复表头；不以缩字达到页数。按内容组织 6–8 个逻辑页组，渲染后的真实页数另验；图表过大或表格换页仍必须修订重渲染。

默认七部分：当前结论、动作与确定性诊断、相机、通用抓持诊断、GPT、teacher 与数据、复现与发布。允许合并为六部分或扩展至八部分，但每个主题必须覆盖。诊断、teacher、GPT 调试与 GPT 正式 cohort 独立声明状态；`closed/not_run/blocked_budget/incomplete` 不能互换。完成计划配额的 closed cohort 必须保留每集，未执行项可以明确写 not_run，不能补造成功。

输入 schema 为 `labsim.Project_v1_1.report_inputs.v1`。主要字段：

- `metadata`：不带标点的纯文本 title、实际日期、读者、作者和开头结论。
- `sources`：`id/scope/path/sha256` 或 `id/scope/url`。scope 明确为 diagnostic、camera、grasp、teacher、gpt_debug、gpt_formal、release、contract 或 history。最终本地来源必须有完整 SHA，并在生成前复核。旧版资料只作固定公开 URL 历史链接，不能当当前数字来源。
- `cohorts`：四类分别给 `kind/status/completed_count/note`。closed 必须引用对应 scope 的 `summary_source`，可给 `planned_count`；不可把计划数当实际数。
- `pages`：每组给纯文本 `title/topics/blocks`。所有页的 topics 合计必须覆盖 summary、executor、camera、grasp、gpt、teacher_data、release。
- `limitations`：必须显式填写实际证据边界和剩余事项，自动写入正文末尾。生成器不对未执行项目推导“通过”。

block 支持 `paragraph/heading/table/figure/links/code/markdown`。表格与正文值可以直接给字符串，也可以给单值 JSON pointer：

```json
{
  "source": "fine_summary",
  "pointer": "/runs/fine_preinsert_02/simulation_seconds",
  "format": ".3f",
  "suffix": " s",
  "null_text": "null 未判定"
}
```

示例 pointer 仅说明语法；必须使用真实最终 JSON 字段路径。源值 null 会保持 null 文义，不能按 false/0 格式化；boolean 保留 true/false。非有限数拒绝作为结果。普通段落承载解释，表格只放短数值/状态记录（2–7 列、最多 18 行）；逐步/逐集大表以 CSV/JSON 链接保留。

`table` 的 `headers/rows/widths/align` 分别为列名、每行值、正权重列宽、每列 left/center/right。`figure` 用 `source/caption/max_height_cm`，源必须是当前 PNG/JPEG。`links` 用 `items:[{"source":"id","label":"描述性文字"}]`，MD 与 DOCX 都生成相对目标。`code` 手动换行到每行不超过 90 字符；建议进一步保持易读的 70–80 字符。

`markdown` 从 sources 指向的当前 MD 读一个已编辑的正文片段，支持段落、纯文本小标题、单层项目符号和 fenced code。带链接、图或表格的完整报告不能直接塞入；应拆成 typed blocks，以明确图片哈希、表列宽和包内依赖。粗体等复杂 inline 样式不由片段解析器处理，最终正文应使用自然连接的纯文本。

本地来源拒绝绝对路径、目录穿越、symlink、LFS 指针、旧版目录及 H5/raw/archive 等非精简格式；图片、视频实体必须先由当前媒体流程准备。这里只验证文件实体与 SHA，不代替完整视频解码、模型实际输入核对或判分。

## 只读校验

先复制模板到独立 `release_inputs.json`，填好当前证据。只用 workspace loader 指定的 bundled Python。以下命令是后续操作说明，本准备轮未执行：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  docs/lab_cuvette_loading/Project_v1_1/report/generate_report.py \
  --inputs docs/lab_cuvette_loading/Project_v1_1/report/release_inputs.json \
  --validate-only
```

模板尚未 final 时只可 `--allow-draft --validate-only`。不加 mode 的默认行为也是只读。只读校验不创建输出目录、不调用 python-docx、不运行 marker。

## 正式生成与渲染

正式输入填写真实日期与全部 SHA，按实际闭合范围确认 `finalized=true`。**首次 DOCX create/edit authoring 命令之前，调用者须按 documents skill 成功执行且只执行一次 marker**；生成器不会自动运行或重复 marker。若其他 agent 已为本次新版请求执行过 marker，继续使用该次记录，不再重跑。

技能：[documents SKILL.md](/home/wujing/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/SKILL.md)。其要求为：“Immediately before the first create/edit authoring command, run mark_artifact_operation_started.mjs successfully exactly once”。模板选择指南已读；此会话没有 list_artifact_templates 工具，继续使用上述朴素技术报告设计。

首次 marker 的命令形式（仅操作说明，本文没有执行）：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  /home/wujing/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/container_tools/mark_artifact_operation_started.mjs \
  --operation-kind create --expected-output-count 1 --output-format docx
```

之后生成 MD/DOCX 与 build 记录：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  docs/lab_cuvette_loading/Project_v1_1/report/generate_report.py \
  --inputs docs/lab_cuvette_loading/Project_v1_1/report/release_inputs.json \
  --author --marker-already-run
```

成品默认名为 `LabSim_Project_v1_1_项目发布与验证报告.{md,docx}`。已存在时拒绝覆盖；QA 修订可显式增加 `--overwrite`，无需重跑 marker。build 文件保存输入/脚本/依赖/输出 SHA、cohort 声明和 `visual_QA_completed=false`；作者必须另外完成真渲染逐页检查记录。

使用既有隔离渲染器和 bundled LO，不改系统 Python/LibreOffice、不安装运行环境：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  docs/lab_cuvette_loading/Env_v1/report/render_docx_isolated.py \
  docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.docx \
  --output-dir /tmp/LabSim_Project_v1_1_report_QA_NEW --emit-pdf
```

逐页以原尺寸打开全部 page PNG，检查中文字体、图注、列宽、边框、表头、溢出与留白；任何修改均重渲染并再次检查全部页。渲染页/PDF是内部 QA，不纳入默认交付小包。build 的 planned_page_groups 不是真实页数；真实页数与检查结论写单独 `render_QA.json`。

## 最终包的链接约束

DOCX 内链接不会由打包脚本改写。包中保留 `Project_v1_1/report` 与每个 `report_relative_target` 的相对目录布局；源码与历史 URL 链接只作追溯，不承诺复制完整工程。最终 allowlist 必须覆盖全部本地媒体链接，遗漏目标不能落为 ignored outputs 的伪 GitHub URL。另见 [只读打包审查](readme_cli_package_review_20261027.md)。

`tests/test_lab_cuvette_project_v1_1_report_builder.py` 只验证输入/证据边界，不生成 DOCX。准备轮仅做 bundled Python 的 AST 语法检查；测试执行和实际 DOCX 排版/渲染尚待后续。
