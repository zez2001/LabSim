# V0_demo02 原视频场景与原生配合核查

本版本尚未完成连续物理装载。新增独立分支 `codex/lab-cuvette-demo02`，保留全部历史版本。已复核实际视频、CAD实例/子集、尺寸和变换，导出源姿态与视频估计近竖直开盖的独立USD；目标参考帧在样品腔内，不接入机外槽。完整白色来源架CAD未找到，源器皿与两原座声明直立路径仍相交；没有新成功H5、标准5次或随机10次结果。

完整 [报告](../../docs/lab_cuvette_loading/V0_demo02/report.md)、[资产对应](../../docs/lab_cuvette_loading/V0_demo02/asset_correspondence.csv)、[尺寸](../../docs/lab_cuvette_loading/V0_demo02/source_audit/dimensions.csv)、[最终场景核查](../../docs/lab_cuvette_loading/V0_demo02/source_audit/final_scene_verification.json)、[静态验收关口](../../docs/lab_cuvette_loading/V0_demo02/acceptance.json) 和 [待补信息](../../docs/lab_cuvette_loading/V0_demo02/required_information.json) 均已保存。

```bash
cd /home/wujing/Desktop/vla/LabSim
# 实际验证过的静态渲染入口，输出必须为新目录。
bash demos/lab_cuvette_demo02/run.sh --review --headless \
  --output outputs/lab_cuvette_loading/V0_demo02/my_static_review
# 去掉 --headless 为GUI静态审核，本轮未另行实跑GUI。
# 当前完整任务入口只保存 BLOCKED_STATIC_ACCEPTANCE，不启动不合格物理任务。
bash demos/lab_cuvette_demo02/run.sh \
  --output outputs/lab_cuvette_loading/V0_demo02/my_workflow_gate
# 使用现有离线USD环境重新派生，拒绝覆盖已有目录。
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo02.build_scene \
  --output outputs/lab_cuvette_loading/V0_demo02/my_assets
# 加 --source-pose 保留原CAD盖板姿态。
# 不按模型文件名筛选的交付归档核查；只读来源，不覆盖既有JSON。
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo02.audit_deliveries \
  --output outputs/lab_cuvette_loading/V0_demo02/delivery_recheck_01.json \
  --bsdtar /home/wujing/anaconda3/bin/bsdtar
```

静态截图是零任务物理步的资产审核，不是自然支撑或操作记录。预览器皿悬置在候选座上方，画面明确标注 unsupported preview。90°盖板是图像估计，围绕几何推测的铰链轴刚体旋转，未改变源部件尺寸，不是真实标定。第二仪器为相同CAD的背景实例，布置关系仅工程估计。

`collector.py` 继承既有采集器；`analyze.py` 修正独立判分及窗口语义；`data_check.py` 使用原加载器检查数据/资格。实际通过的是历史记录只读回算、元数据正反例及新空索引拒绝。数据字段契约、拒绝证据和命令见 [数据审核](../../docs/lab_cuvette_loading/V0_demo02/data_audit/README.md)。未把旧demo01成功数据改标为demo02，也未制造成功训练batch。

静态关口通过后仍须实施新架/座的完整控制适配、全手爪与机器人碰撞和可达性、一次真实连续任务及其采集，再依次进行5次固定与至少10次合法跨槽/布局随机检查。现有配置的240Hz/60Hz和50µm门槛保留；合法随机范围及槽位ID尚未有数据依据。
