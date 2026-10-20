# 最新进展 V0 demo03

2026-10-20：取得一条白色6×6架取物至开盖仪器腔内A派生座的完整连续成功轨迹，61.75秒，实际松爪和撤离后稳定3.1秒，独立15项检查与H5资格一致。当前正在固定5次复测，随机10次及成功batch读取结果随后补充。该适配模式不改写native_pair_success或real_calibrated。

分支：`codex/lab-cuvette-demo03`。详见[本轮报告](docs/lab_cuvette_loading/V0_demo03/report.md)和[启动命令](demos/lab_cuvette_demo03/README.md)。

# LabSim 进展与分享入口

当前分享分支为 `codex/lab-cuvette-demo02`。本分支包含从 minimal_pick 到 V0_demo02 的开发历史，`main` 保持 LabUtopia 上游基准。仓库当前是私有的，接收方需要相应 GitHub 访问权限。

给其他 agent 的可传输阅读包统一按 [结果阅读包规范](docs/agent_handoff/README.md) 生成。当前桌面目录为 `/home/wujing/Desktop/LabSim_截至V0_demo02_结果阅读包_20261020`，先读包内 `00_给Agent阅读说明.md`；包括系列背景、本轮报告、成功及失败录像、结果表和精简证据。以后每次改进交付创建新包，保留旧包。

- [系列实验总报告 DOCX](docs/series_20261019/LabSim系列实验总报告20261019.docx)
- [适合 Agent 阅读的完整报告](docs/series_20261019/report.md)
- [11 段代表录像](docs/series_20261019/media)
- [精简结果与资产依据证据](docs/series_20261019/evidence)
- [各复制材料的来源与 SHA256](docs/series_20261019/source_manifest.json)

## V0_demo02 本轮状态

V0_demo02尚未完成正确场景内的连续物理装载。实际原视频核查得到6×6白色多孔架和两台仪器，纠正旧6×8假设及任务仪器混淆。已有CAD实例代理共8网格，未找到完整来源架；源盖板主面41.566965°，派生层刚体增转48.433035°到图像估计90°。腔内A/B仅暂定映射；两个原座与14.85mm器皿的声明竖直居中姿态各有40个截面相交见证。没有缩模、删座或用机外槽替代终点。

已实际完成源附件/深层USD/最终场景审计、独立USD保存重载、四视角Isaac零步静态图、历史seed7000判分语义修正、新采集元数据与失败/空索引拒绝核查。完整任务、5次标准、10次合法随机、新成功H5及训练batch均未执行。原失败、原评分和旧H5保留。

- [V0_demo02结果报告](docs/lab_cuvette_loading/V0_demo02/report.md)
- [本轮DOCX](docs/lab_cuvette_loading/V0_demo02/LabSim_V0_demo02_场景与装载关口报告_20261020.docx)
- [资产对应CSV](docs/lab_cuvette_loading/V0_demo02/asset_correspondence.csv) · [实算尺寸及变换](docs/lab_cuvette_loading/V0_demo02/source_audit/final_scene_verification.json)
- [实际静态截图](docs/lab_cuvette_loading/V0_demo02/static_review) · [独立验收状态](docs/lab_cuvette_loading/V0_demo02/acceptance.json)
- [三项集中待补资料](docs/lab_cuvette_loading/V0_demo02/required_information.json) · [数据接口核查](docs/lab_cuvette_loading/V0_demo02/data_audit/README.md)

## 历史实验结论

minimal_pick 已完成独立物理抓取、数据采集与动作回放；ACT/DP 仅做过极短训练链路检查，短训练策略未抓取成功。合成直孔实验观察到亚毫米偏差导致的结果变化，但边界对物理与接触配置敏感，不构成真实精度验证。

V0 为图像关系参考下的 Python 参数化代理场景，完成标准、随机、采集和回放的声明批次。外部文件尺寸资产接入后，原生配对仍有身份及几何关口。V0_ext02 的 28 块厚壁器皿通过独立支撑和抓取搬运诊断，最终停在松爪前检查，未完成经判分通过的释放闭环。不要把 V0 成功、外部资产诊断进展和原生完整装载混为一谈。

V0_demo01 已在明确新增的来源工装和仪器前侧目标工装中完成连续取出、搬运、装载、交接、松爪、撤离和3秒观察。固定配置5/5独立通过；工装XY各±1mm的小范围随机2/3通过。seed7000在OPEN时源底面穿入0.050289mm，超过既定0.050000mm门槛，保留失败，未放宽标准。原生配对未执行，native_pair_success及原任务full_success仍为false。

- [V0_demo01 完整补充报告 DOCX](docs/lab_cuvette_loading/V0_demo01/LabSim_V0_demo01_连续装载结果报告_20261019.docx)
- [V0_demo01 Agent阅读报告与复现入口](docs/lab_cuvette_loading/V0_demo01/report.md)
- [1080p单次连续成功主录像](docs/lab_cuvette_loading/V0_demo01/media/engineering_workflow_success_1080p.mp4)
- [全部固定与随机结果 JSON](docs/lab_cuvette_loading/V0_demo01/results.json)
- [随机释放失败及慢放](docs/lab_cuvette_loading/V0_demo01/media)

系列总报告保留截至ext02的历史，V0_demo01结果独立补充；工程工装成功不能解释为原外部器皿与原装载座配套成功。原始H5和逐物理步接触记录保存在本机outputs，精简证据与代表录像随Git分享。

## 克隆与查看

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch \
  --branch codex/lab-cuvette-demo02 \
  https://github.com/zez2001/LabSim.git
cd LabSim
git lfs pull --include="assets/robots/Franka.usd,assets/beaker.usda,assets/lab_cuvette_loading/**,docs/**"
```

代表录像、报告和小型结果已随 Git 保存；完整 `outputs`、H5、逐物理步轨迹、环境和训练检查点未上传。运行需要已有兼容 Isaac Sim 环境，启动命令见各任务 README。若仅阅读代码可先跳过 LFS，查看图表及运行则需获取相应对象。

## 任务入口

- [最小物理抓取及数据管线](demos/minimal_pick/README.md)
- [亚毫米插入](demos/minimal_precision_insertion/README.md)
- [V0 完整代理任务](demos/lab_cuvette_loading/README.md)
- [ext01 外部资产及关口](demos/lab_cuvette_external/README.md)
- [ext02 支撑与抓取搬运诊断](demos/lab_cuvette_ext02/README.md)
- [V0_demo01 连续工程任务](demos/lab_cuvette_demo01/README.md)
- [V0_demo02 视频场景与原生装载核查](demos/lab_cuvette_demo02/README.md)

离线 ext02 判分需要加载 USD 库路径：

```bash
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_ext02.analyze_table <trial目录>
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_ext02.audit <支撑记录目录>
```
