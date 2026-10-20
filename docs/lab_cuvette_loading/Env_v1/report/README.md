# Env v1 本轮报告生成器

`generate_report.py`只读取本轮 Env_v1 输出及实证文件，生成计划6页的中文 DOCX、同内容 Markdown 与来源哈希 JSON。页面为完成矩阵、场景/相机、原座几何、控制结果与对照、三策略/API、数据复现与实物缺口。它不运行仿真、不改变结果、不复制 HDF5、不渲染或调用 LibreOffice。2026-10-21 已完成语法及只读证据收集检查；此准备阶段没有运行 DOCX authoring 或 artifact marker。

生成前冻结本轮输出，并按 documents 技能要求成功运行一次创建标记；生成后必须用技能内 `render_docx.py` 渲染并查看所有页 PNG。主任务负责此流程。使用已由 workspace loader 解析的 bundled runtime，不能改用系统 Python 或系统 LibreOffice：

```bash
/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
 /home/wujing/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/container_tools/mark_artifact_operation_started.mjs \
 --operation-kind create --expected-output-count 1 --output-format docx

/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
 docs/lab_cuvette_loading/Env_v1/report/generate_report.py \
 --evidence-manifest <本轮最终证据选择JSON> --output <不存在的新报告目录> --copy-media

/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
 /home/wujing/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/render_docx.py \
 <报告DOCX路径> --output_dir <独立QA目录> --emit_pdf
```

当前技能 renderer 的 `_resolve_soffice` 根据所选 Python 查找 `dependencies/bin/override/soffice`，并在 bundled office 缺失时直接报错；不静默回退系统 LibreOffice。以上命令在准备阶段均未执行，不能据此声明 DOCX 已生成或排版已验收。

可选 manifest 格式如下。所有路径相对于工程根目录；进程退出码只能来自实际保存的进程证据 JSON。没有时报告保留未知，不能由场景结果推断正常退出。`checks`读取真实JSON指定字段再对比，不接受无证据的完成声明。

```json
{
  "run_names": ["preview_03", "preview_04", "grasp_hold_01", "grasp_hold_02"],
  "policy_attempt_dirs": [],
  "run_process_evidence": {
    "preview_04": "docs/lab_cuvette_loading/Env_v1/runtime/preview_04_process.json"
  },
  "figures": [
    {"role": "scene", "path": "outputs/lab_cuvette_loading/Env_v1/preview_04/episode_0000/side_camera_initial.png", "caption": "实际侧视初帧"}
  ],
  "media": [
    {"label": "本轮预览连续双视角", "path": "outputs/lab_cuvette_loading/Env_v1/preview_04/episode_0000/dual_view.mp4"}
  ],
  "checks": [
    {"label": "新episode正常读取", "evidence": "<实际读取验证JSON>", "json_key": "verified", "equals": true}
  ]
}
```

未指定 manifest 时自动发现已落盘的新场景结果和策略尝试，并选已完成运行的实际初帧及几何图。`policy_attempt_dirs`只选择最终主证据，不过滤全部尝试统计；旧失败及观测边界不合格尝试始终保留。媒体存在不等于画面验收通过。建议最终交付指定已检查的图片与少量代表录像，`--copy-media`会复制它们，Markdown和Word媒体超链接使用包内相对路径。无该选项时原媒体外链不构成便携交付。

`run_names`和可选`episode_directories`只选择正文主展示，全部已完成新run结果仍入证据和数量，不隐藏旧失败。`figures.role`支持`reference`、`scene`、`geometry`、`control`；可用`max_height_cm`和`max_width_cm`设置图片占位上限，control默认10cm高，其余6.2cm，最大宽默认16cm。可选`renderer_audit`指向实际最新渲染关联审计；默认优先读取preinsert的4958/4958证据，旧extract01的0.966mm只作为修复前记录。`dataset_group_evidence`用于最终数据分组JSON，`reproduction_commands`为准确复现命令字符串列表。continuous_latch与后续preinsert只在result.json落盘后读取其真实阶段和整体判分，不提前写success。

`plot_control_overview.py`从四条已关闭H5的控制观测和后继状态生成`data/control_results_compact.png/JSON`，包含实际底面抬升、手内原点漂移、执行开度及latch局部放大。图只展示控制采样，240Hz独立判分原结果另留JSON。生成器同时读取真实15周期回放和阅读版媒体来源，不把回放或压缩录像称为完整装载成功。

策略状态分为接口实际连通与观测边界合格：Astra/Harness按实际保存的RPent工具状态中相机元数据检查当前明确白名单；π0.5按实际模型服务器输入日志检查双RGB与本体状态字段。完整原始相机元数据仅留审计，不应提供给视觉策略。Astra02的5个真实动作保留为接口历史，但其工具返回曾包含renderer/debug/depth统计，不计合格链路；Astra03独立重跑的严格观测边界另行检查。Astra01的0动作仍保留为未连通尝试。报告不会因选择新轨迹而隐藏这些记录。

范围规则：历史任务结果仅用于明确标注的回归；新完整成功与有效失败只按新任务独立判分及采集器最终资格统计。纯checkpoint加载、访问探测及合成单元测试均不计策略闭环或物理成功。报告生成时读取新文件，不沿用当前准备时点的运行状态。
