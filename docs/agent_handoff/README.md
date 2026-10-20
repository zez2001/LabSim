# Agent 结果阅读包

每次改进交付创建新的可传输结果文件夹，保留旧包。当前清单包含系列历史、demo01工程任务、demo02场景核查与demo03正确场景内连续装载结果。只整理报告、必要录像、图表、判分和精简数据样例，不复制整个工程、环境、原始H5或接触大数据。

```bash
cd /home/wujing/Desktop/vla/LabSim
python3 scripts/package_agent_results.py \
  --output /home/wujing/Desktop/LabSim_截至V0_demo03_结果阅读包_20261020
```

先更新[材料清单](package.json)与[先读说明](00_给Agent阅读说明.md)，提交并推送验证后的改动，核对远端SHA后再生成包。输出必须不存在；同日多轮加编号。桌面副本不重复加入Git，源材料与脚本随开发分支上传。

脚本使用Python标准库，复制实际文件，无本机软链接；缺少LFS实体即停止。包内报告和图像保留相对路径，包外源码引用转换为来源提交GitHub链接。文件清单记录源SHA与包内SHA，区分Markdown链接改写；生成时间、分支和来源提交写入根说明。生成后逐条校验文件与相对链接，检查四份主要DOCX、新成功和历史失败视频、结果表与真实batch样例。

```bash
cd <收到的结果阅读包>
sha256sum -c SHA256SUMS.txt
```

V0_demo03有新场景实际成功轨迹和真实batch。旧demo01机外工装、demo02原尺寸阻塞等历史资料分别保留原范围，不能混作demo03或原CAD配套成功。仓库私有；阅读包可离线整体传输，源码链接需要GitHub权限。
