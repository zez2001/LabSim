# LabSim 进展与分享入口

当前分享分支为 `codex/lab-cuvette-external-assets`。本分支包含从 minimal_pick 到 V0_ext02 的开发历史，`main` 保持 LabUtopia 上游基准。仓库当前是私有的，接收方需要相应 GitHub 访问权限。

- [系列实验总报告 DOCX](docs/series_20261019/LabSim系列实验总报告20261019.docx)
- [适合 Agent 阅读的完整报告](docs/series_20261019/report.md)
- [11 段代表录像](docs/series_20261019/media)
- [精简结果与资产依据证据](docs/series_20261019/evidence)
- [各复制材料的来源与 SHA256](docs/series_20261019/source_manifest.json)

## 当前结论

minimal_pick 已完成独立物理抓取、数据采集与动作回放；ACT/DP 仅做过极短训练链路检查，短训练策略未抓取成功。合成直孔实验观察到亚毫米偏差导致的结果变化，但边界对物理与接触配置敏感，不构成真实精度验证。

V0 为图像关系参考下的 Python 参数化代理场景，完成标准、随机、采集和回放的声明批次。外部文件尺寸资产接入后，原生配对仍有身份及几何关口。V0_ext02 的 28 块厚壁器皿通过独立支撑和抓取搬运诊断，最终停在松爪前检查，未完成经判分通过的释放闭环。不要把 V0 成功、外部资产诊断进展和原生完整装载混为一谈。

最新授权接续版本为 V0_demo01：保留 native_pair 原生几何关口，另以明确可见的工程工装完成连续取出、搬运、装载、释放与撤离。系列报告截止 ext02，不包含尚未执行的新任务结果；后续结果另立版本记录。

## 克隆与查看

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch \
  --branch codex/lab-cuvette-external-assets \
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

离线 ext02 判分需要加载 USD 库路径：

```bash
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_ext02.analyze_table <trial目录>
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_ext02.audit <支撑记录目录>
```
