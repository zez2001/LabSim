# series_20261019 历史 DOCX 归档试点

本试点只选择 `docs/series_20261019/LabSim系列实验总报告20261019.docx`，共 **2,100,765 字节**。它保留截至 ext02 的历史结果，不代表本轮新增物理实验或当前默认 demo。11 段历史录像、Markdown、图表、JSON 和其他 DOCX 均保留原位。

当前状态：**归档已发布；3 个附件均从公开下载地址重新取回并通过字节数和 SHA256 核对，下载 ZIP 已恢复且逐文件与移除前的原 DOCX 完全一致。专用整理分支已移除此 DOCX，原始工作区仍保留。**

Release ID 为 `434619795`，发布时间为 `2026-11-05T00:26:36Z`（北京时间 08:26:36），tag 指向下述完整基线提交。远端发布后才完成下载核验、独立目录恢复和本分支移除；没有改写原始历史记录。已上传 manifest 保持原字节，发布与恢复状态记录在本页。

固定来源提交为 `137f1b20b36f821894b6387ba36ee592231c8b1f`。该 DOCX 是普通 Git blob，未读取或下载任何 LFS 内容；归档前已核对当前专用工作区字节与该提交完全一致。

- [完整机器清单与逐文件 SHA256](manifest.json)
- [已发布 Release](https://github.com/zez2001/LabSim/releases/tag/archive-series-20261019-20261105)
- [ZIP 下载](https://github.com/zez2001/LabSim/releases/download/archive-series-20261019-20261105/LabSim-series_20261019-docx-137f1b20.zip)
- [manifest 下载](https://github.com/zez2001/LabSim/releases/download/archive-series-20261019-20261105/LabSim-series_20261019-docx-137f1b20.manifest.json)
- [SHA256SUMS 下载](https://github.com/zez2001/LabSim/releases/download/archive-series-20261019-20261105/LabSim-series_20261019-docx-137f1b20.SHA256SUMS.txt)

ZIP 为 **2,100,985 字节**，SHA256 为 `6f19760443cf1905afb561ba80b721f78400a75bc6761d0e917ed743989c6a5c`。其中 DOCX 的 SHA256 为 `cb6d6ff3521f181f20f56c913395aaf7d4700ddd50cf12f15a3f6534d16493fe`。ZIP 只包含这一原路径下的原字节 DOCX，不是完整历史阅读包。

manifest 为 6,105 字节，SHA256 为 `d5248163b43d7969f1856aa1923875077637cf60eec2013eea4daa58dbe9226d`；SHA256SUMS 为 224 字节，SHA256 为 `d0c8b7b14ab7c209abc179fb31b89f712c720311c974688945fc0f77a295c545`。本机验证记录保存在被忽略的 `outputs/projectization_round2/20261105_081353/evidence/` 下的 `archive_publication.json`、`archive_release_restore.json`、`archive_verified_before_deletion.json` 和 `archive_removal_receipt.json`。

## 查看与原路径映射

优先从[固定提交的总报告](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/series_20261019/report.md)阅读上下文；其相对录像、图表与证据链接仍指向相同提交。原 DOCX 可从[固定提交目录](https://github.com/zez2001/LabSim/tree/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/series_20261019)获得。ZIP 内文件名与 manifest 的 `files[].path` 完全相同。

[原进展入口](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/LABSIM_PROGRESS.md)、[原来源清单](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/series_20261019/source_manifest.json)及旧的 render/preservation JSON 保持原始字节。它们记录当时的路径和状态；本页提供当前取回映射，不回写历史记录。

当前统一历史导航使用本页作为 DOCX 获取入口。运行、配置、测试及 16 份阅读包配方均未选择此文件。旧 `demos/lab_cuvette_demo02/preservation.py` 会递归快照当时存在的文件；它保留原行为。核验曾包含该 DOCX 的旧快照时，应使用固定基线或在新目录恢复完整所需材料，不能把当前少一个历史 DOCX 的树与旧完整快照直接比较。

## 验证与恢复

在项目根目录执行，`--archive` 改为已下载 ZIP 的路径。只验证时不创建目录：

```bash
python scripts/restore_history_archive.py \
  --manifest docs/archive/series_20261019/manifest.json \
  --archive /tmp/LabSim-series_20261019-docx-137f1b20.zip
```

恢复目录必须尚不存在，且位于现有 Git 工作区之外。下面命令保留原目录结构，不覆盖仓库中的文件：

```bash
python scripts/restore_history_archive.py \
  --manifest docs/archive/series_20261019/manifest.json \
  --archive /tmp/LabSim-series_20261019-docx-137f1b20.zip \
  --restore-to /tmp/labsim-series-20261019-restored
```

恢复后文件位于 `/tmp/labsim-series-20261019-restored/docs/series_20261019/LabSim系列实验总报告20261019.docx`。工具先验证 ZIP 大小、SHA256、完整成员集合和逐文件 SHA256，再创建输出；拒绝路径穿越、软链接、重复、缺失或多余成员及覆盖。恢复单一 DOCX 不会补齐报告中的其他材料；完整历史上下文使用上面的固定提交链接。

选择前复核了审计 CSV、67 个额外保留路径、26 组依赖例外、65 个同学增量路径以及动态扫描和打包配方，交集为空。此检查不能证明仓库外不存在消费者；如依赖本地旧路径，请使用本页的固定来源或恢复到独立目录。
