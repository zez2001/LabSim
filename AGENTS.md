# LabSim 协作规则

## 授权与工作区

当前用户指令优先于仓库规则。仅在用户授权的 checkout、分支和任务范围内工作；开始前检查 Git 状态，保留他人的未提交修改。提交、推送、创建 PR、发布 Release/HF、导出副本或结果包分别按当前会话授权执行，未获授权时完成本地验证并报告状态。历史上传或打包授权不自动延续到新任务；不强推、不静默覆盖、不改变仓库可见性。

使用当前授权的开发线；独立功能需要分支时采用 `codex/<feature>`。不要把历史日期分支当作当前默认入口。分支清理须核对合入情况、开放 PR 和 worktree，保留可恢复标签。

## 保存位置与保护边界

- Git：代码、配置、协议、当前文档、依赖清单及 CPU/运行需要的必要小型 fixture。
- Hugging Face：明确版本、许可与哈希的大型数字资产和正式数据集；发布需单独授权，不能仅凭目录名推定已发布。
- 本地忽略目录：`outputs/`、`results/`、`local_assets/`、`local_setup/`、`test_outputs/` 保存运行输出、结果和缓存。现有无根锚 ignore 规则同时覆盖根目录与嵌套生成目录，不机械添加根锚；既有 tracked 证据不因 ignore 规则而删除或取消跟踪。
- GitHub Release：获授权的里程碑、历史结果包和代表视频；记录固定源码提交、资产/数据版本与文件 SHA256。Release 与 HF 发布状态须实际核验。

保留原 CAD、资产、配置、报告、录像、H5、标签、源路径和源码指纹的原字节。不得按扩展名或“零字符串引用”批量迁移/删除；`docs/` 中还包含运行门禁、动态导入工具、测试输入及打包清单。交付副本省略某类文件不构成从 Git 删除的依据。派生报告或新实验使用新路径，并绑定原始来源；冻结物理、动作或评分变化必须建立新版本。

## 验证与报告

入口变更提供帮助、错误提示、防覆盖和适当 CPU 检查。准备提交时先运行 `git diff --cached --name-status` 人工核对暂存清单，仅包含本次授权路径，再运行 `python3 -B scripts/check_repository_changes.py` 检查暂存内容；范围比较用 `--base <base-ref> --head <head-ref>`。检查规则及既有忽略例外见 `config/repository_hygiene.json`、`config/repository_hygiene_legacy_ignored.json`。

CPU 检查不证明 Isaac 物理接触、真实模型或真机校准。分别记录已运行、失败、未执行、进程退出及数据闭合状态；完整成功包含实际释放、脱指、撤离和至少 3 秒稳定。Size_v1 正式采集/训练准备保持 standard，场景随机化关闭，训练 RNG 单独配置。不得重写失败标签或将计划配额写成已完成。

README 保持稳定使用入口，过程及逐轮结果通过[统一结果索引](docs/history/RESULTS.md)导航。交接更新遵循 [CONTRIBUTING](CONTRIBUTING.md)、[交付边界](DELIVERY.md)和[结果阅读包](docs/agent_handoff/README.md)；纯工程整理不重复复制旧报告和大视频。

## 历史授权记录

下列固定提交保留原授权的日期、范围和例外，仅供追溯：

- [原 AGENTS：2026-10-19/20 与 2026-10-27 规则](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/AGENTS.md)。
- [原贡献规则](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/CONTRIBUTING.md)、[原交付记录及当时 PR/分支](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/DELIVERY.md)。
- [原阅读包与数字资产交付范围](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/agent_handoff/README.md)、[分支归档清单](docs/development/branch_archive_20261022.json)。
