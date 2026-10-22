# Agent结果阅读包：当前 Size_v1

当前 [package.json](package.json) 只选择本轮两个目录：

- `docs/lab_cuvette_loading/Size_v1/results_20261021`：最终DOCX/Markdown报告、必要图片及代表连续录像。
- `docs/agent_handoff/Size_v1_current`：固定标准场景、资产尺寸假设、几何与物理摘要、实际结果/配额、读取资格及准确调用命令。

目标小于20MB。旧 V0、Env_v1、各 demo 的目录与桌面阅读包保持原样；切换前的清单和说明已经独立保存到 `history/handoff_before_Size_v1_*`。不复制全部35个资产实体、原始H5、JSONL日志、环境或模型检查点。完整便携episode单独提供。

最终运行闭合并审计后，刷新小证据。若尚无最终审计，配额必须保持 unavailable，不能提前写成20成功+20失败：

```bash
cd /home/wujing/Desktop/vla/LabSim
python3 scripts/refresh_lab_cuvette_size_v1_handoff.py --refresh \
 --summary outputs/lab_cuvette_loading/Size_v1/summaries/FINAL_SNAPSHOT/summary.json \
 --collection-audit outputs/lab_cuvette_loading/Size_v1/collection_standard/FINAL_AUDIT.json
```

没有最终审计时可省略两个可选参数；此时只快照已闭合的原始结果，并明确不宣称采集配额。刷新脚本不生成报告、不启动仿真、不生成最终阅读包。

检查报告所有视频、图片、CSV、配置引用均存在、DOCX相对media链接有效，且当前结果与独立评分一致。然后提交并推送、核对远端SHA，最后才生成全新的桌面包：

```bash
python3 scripts/package_agent_results.py \
 --output /home/wujing/Desktop/LabSim_Size_v1_本轮改动与结果_精简阅读包_20261021
```

输出目录必须不存在；此说明不代表已经打包或上传。生成后检查总量小于20×1024×1024字节，并执行 `sha256sum -c SHA256SUMS.txt`。包根清单记录最终分支、提交、源文件及SHA256；不要在报告或快照中猜测尚未产生的最终提交。

本轮研究的是“原座不改，统一XY变换的比色皿尺寸假设”。实际完整任务结果、固定5次验证及20/20配额均以本轮最终证据为准；几何证书、preview、预插入、开发成功和进程中断不能混算为正式合格采集。random10已经从本轮验收中取消，训练及自动验证保持standard。`real_calibrated`与原12.5mm配套结论不因新尺寸成功而改变。

通过真实固定5次验证并显式放行后，自然采集与受控失败可交错。优先自然失败；允许先运行1条完整任务的INSERT确定性提前停，确认失败标签、元数据与读取链路，再补采其余20/20缺口。它没有缩短环境预算，不能与短预算接口诊断混算；采集driver因总配额未满退出2与仿真子进程非零退出必须区分。
