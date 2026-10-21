# Agent结果阅读包：当前Env_v1

当前选择[package.json](package.json)仅包含两个目录：

- `docs/lab_cuvette_loading/Env_v1/results_20261021`：本轮最终报告及其自带media。
- `docs/agent_handoff/Env_v1_current`：本轮预插入/历史失败/replay/三链/API摘要、完成矩阵、状态、资产尺寸及全部当前配置。

目标小于20MB，不包含整套历史、outputs、H5、环境、checkpoint或桌面2546460010字节的preinsert01便携episode（旧extract01约451MB亦不打包）。旧V0_demo04_current和旧阅读包保留；此前清单/说明另存history。报告目录尚在归档时不能先执行打包或宣称包已生成。

根任务应在最终trial落盘后刷新Env_v1_current中的配置、矩阵、状态及version.json来源哈希。确认报告引用的DOCX、Markdown、视频、图片、CSV和必要JSON均存在，media只含本轮必要证据，并确认总量小于20MB。核查[先读说明](00_给Agent阅读说明.md)的计划包内链接后，提交并推送已验证改动、核对远端SHA，再执行：

```bash
cd /home/wujing/Desktop/vla/LabSim
python3 scripts/package_agent_results.py \
 --output /home/wujing/Desktop/LabSim_Env_v1_本轮改动与结果_阅读包_20261021
```

必须使用不存在的新输出目录，保留旧包；本文不是已打包或已推送的证明。生成后检查脚本返回的bytes小于20×1024×1024，并在包根执行：

```bash
sha256sum -c SHA256SUMS.txt
```

脚本复制实体文件，不保留软链接，LFS实体缺失会停止；最终分支、提交、来源及SHA写入包根清单。普通Markdown引用自动改为包内链接或固定提交源码链接。根先读说明直接使用计划包内相对路径，需在最终生成前逐项核对。DOCX的视频为同级media相对链接，不能只传DOCX。

当前Env_v1完整原座装载未完成。最新82.65秒/4958步预插入诊断通过清槽、搬运、预对准及持物回退，未插入、松爪或脱指撤离；旧42.3秒hold超200μm失败保留。三条策略各0.25秒属于真实接口验证，15tick replay仅短诊断，random API初始化不属于正式任务批次，完整loading成功/有效失败配额0/0。以上边界与最终报告、视频标注、评分及摘要必须一致。
