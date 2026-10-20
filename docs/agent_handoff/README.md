# Agent 结果阅读包

每次改进交付创建新的可传输文件夹，保留旧包。本轮清单保留系列历史、demo01–03，并新增demo04报告、真实受限诊断及失败录像、原座干涉证据、全部判分和完整数据读取验证。按本轮明确的数据交付要求，另外包含一条885 MB自含H5及压缩逐步物理/接触记录，超出通常仅打包精简样例的默认范围；没有复制整个工程或环境。

```bash
cd /home/wujing/Desktop/vla/LabSim
python3 scripts/package_agent_results.py \
  --output /home/wujing/Desktop/LabSim_截至V0_demo04_结果阅读包_20261020
```

先更新[材料清单](package.json)与[先读说明](00_给Agent阅读说明.md)，提交并推送验证后的改动，核对远端SHA后生成包。输出必须不存在；同日多轮加编号。桌面副本和完整H5不重复加入Git，代码、配置、资产、报告和精简视频证据随开发分支上传。

脚本复制实际文件，不保留软链接；LFS实体缺失会停止。Markdown引用重定位为包内相对路径或固定提交源码链接。DOCX中的录像是同级media相对链接，不是嵌入视频；传输整个文件夹，并可直接打开MP4。包内文件来源SHA、打包后SHA和实际分支提交记录在根清单。

```bash
cd <收到的结果阅读包>
sha256sum -c SHA256SUMS.txt
```

检查最新报告的DOCX/Markdown、全部引用视频/图片/CSV/配置、独立判分与第06目录完整H5。demo04几何关口仍失败，完整装载未执行；完成的是到座口上方停止并上抬的诊断。H5的complete仅表示记录闭合；workflow_success/native_pair_success/data_eligible保持false，现有成功过滤器拒绝，显式诊断读取通过。不能将旧demo03的16 mm座成功或demo04的可读数据当成本轮原座成功。

GitHub当前显示仓库公开，源码可直接访问；阅读包可离线整体传输。
