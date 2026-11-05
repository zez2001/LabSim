# 结果阅读包

是否生成阅读包、导出代码或发布，以[当前授权规则](../../AGENTS.md)和本次任务为准。需要阅读包时选一个新目录，只收本轮新增材料；保留旧包，不复制完整工程、环境、原始大 H5 或模型权重。纯工程管理、文档或接口整理通过[统一结果索引](../history/RESULTS.md)及固定提交链接引用旧报告和视频。

包内说明用途、实际已运行/失败/未执行、来源提交与哈希、缺失依赖和剩余问题。新实验按需要包含报告、代表录像、结果表、配置与独立评分证据，并保持相对媒体结构。任务结果、环境有效性、记录完整性和数据资格分别报告，不以正常退出冒充任务成功。

## 历史清单与来源

根[默认清单](package.json)及带 `_current` 的历史目录是已有交付配方，不保证对应当前任务或可由新检出独立重建。它们可能选择被忽略的原机 `outputs/`；缺失项必须报告 unavailable，并通过原保管者/发布入口回取，不能补造、替换标签或静默下载。

- [debug04 工程包](Gpt_debug04_v1_current/package.json)及[汇报包](Gpt_debug04_v1_current/report_package.json)。
- [Policy_eval 工程包](Policy_eval_v1_current/package.json)及[汇报包](Policy_eval_v1_current/report_package.json)。
- [Progress](Progress_v1_current/package.json)、[Internal_use](Internal_use_v1_current/package.json)、[Project_release_v1](Project_release_v1_current/package.json)、[Project_v1_1](Project_v1_1_current/package.json)、[Project_v1](Project_v1_current/package.json)。
- [纯项目交接清单](project_handoff/package.json)；当时数字资产唯一交付目录及特定旧包清理授权保留在[固定提交原说明](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/agent_handoff/README.md)，不扩展为新任务的清理许可。

原清单、先读说明、来源路径和报告保持原字节；为新任务另建清单。source 指向真实仓库内文件，destination 留在包内。清单可组合 `directories`、`files` 和 `readme`；参考现有 JSON schema，不改写旧配方冒充本轮成果。

## 生成与验证

先逐项检查 readme、文件和递归目录的实体是否存在，排除未下载 LFS 指针，确认所有包内/未复制引用的依赖。将本轮材料区分为 Git 固定提交内容与原机 external evidence；后者记录原路径、字节数及 SHA256，单独说明并未由 Git 恢复。

当前打包脚本没有 draft/final 或远端发布验证门禁：它读取工作树字节，并将未复制链接拼到 HEAD。最终提交包应在指定提交的干净独立 checkout 制作，先核对选中 Git 来源与该提交同字节、每个未复制链接确实存在于该 Git tree，再运行：

```bash
python3 -B scripts/package_agent_results.py \
  --manifest docs/agent_handoff/project_handoff/package.json \
  --output /path/to/new-reading-package
```

按任务替换清单及新输出路径。脚本拒绝越界、symlink、目标冲突、LFS 指针和覆盖已有目录；已复制的 Markdown 链接转成包内相对链接。DOCX 的相对媒体在作者阶段核对并随包复制。使用工作树材料制作预览时明确标为 draft，不能据其 HEAD 字段声称与已发布提交一致。

包根 `文件清单.json` 记录实际 HEAD、分支、来源及复制后哈希；`SHA256SUMS.txt` 用于传输检查：

```bash
cd /path/to/reading-package
sha256sum --check SHA256SUMS.txt
```

在移开原工程后核对包内链接、媒体实体、配置/报告引用、缺失来源和总大小。只有本次任务授权推送/发布时才执行，并另行核验远端提交与上传后文件 SHA256；离线通过只能记本地验证，不声称已上传。不要预填未来 SHA，或把旧报告称为本轮新运行。

## 数据与历史保护

完整 H5 与模型日志留在本地输出或单独获授权的数据交付中。HDF5 外链索引须连同源文件移交，或另建带来源的 copy 派生物。Size_v1 40 集的历史最终审计见[原证据](../lab_cuvette_loading/Size_v1/data/final40_actual/README.md)，不得把计划数量写成完成数量。刷新小型快照与构建派生报告均不构成修改原始标签、源 CAD、配置指纹或历史媒体的授权。
