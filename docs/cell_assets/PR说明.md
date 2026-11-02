# 单细胞仪器 unit、expert 数据与策略评测接口

本轮 PR 说明；旧 PR #1 已关闭，按最新授权以 `codex_junjie_1102` 提交至 `codex/labsim`，不自动合并。

## 问题与实现

新增仪器原先只有加载／回放或独立演示，无法直接按当前 LabSim 方式生成 expert 数据和评测 policy。本改动提供五个单细胞测序 unit：IKA 开盖、DIYNAFLUOR 取帽、Flex 装空架、MagSep 空架搬运和 PCR 小试管入孔；统一通过 `./labsim unit`、Python facade 及 loopback RPC 调用。

复用 `Project_release_v1` 的动作执行、回执和策略接口，以及原设备导入／接触场景。PCR 孔腔和 6 mm 小管为单独的工程派生几何，参数未经过厂家或真机校准，盖子预先打开；不修改源资产缓存。

修复 π0.5 亚毫米位移被 IK 容差忽略的问题，记录实际末端移动；Flex／MagSep 增加放置初态，expert 准备与 policy 控制分别计时、录像和判分。模型可失败，不将调用成功、掉落到目标或 expert 准备计为策略完成。

## 验证与边界

- 已有五个 expert 任务通过，共 3990 个选中 transition；GPT-6 与 π0.5 均真实运行，策略任务仍失败。完整证据与预算见 [unit 交接](单细胞Unit验证.md)。
- 代码复核修正启动参数、初始化失败清理、完整动作块检查、开盖撤离稳定判定和 PCR 入孔判定，并将 unit 测试加入 CPU CI。新场景／评分版本为 v2，旧 v1 记录保留，不重写。
- CPU、GPU 复验及文档检查的当前结果见 [代码复核](代码复核.md)；CPU 通过不能代替 GPU 或真机验证。
- OpenFlexure 夹指干涉、三类缺失整机及现场测量仍未解决；不涉及训练、热循环、移液、磁珠或液体过程。

## 获取与复现

基线为此前 rebase 的 `ab519ed`，本地 HEAD `2294a17`；本轮已重新核对远端、fetch 并在 `codex_junjie_1102` 执行 rebase，无冲突。该引用在核对时仍为上述基线，不直接改写集成分支。

```bash
./labsim unit list
./labsim unit collect --unit pcr_insert --headless --output outputs/pcr_NEW
./labsim unit dataset-check --path outputs/pcr_NEW/episode_0000
python -m pytest -q tests/test_cell_units.py tests/test_cell_assets.py
```

环境、参数单位、API、GPT 与 π0.5 配置见 [unit README](../../demos/cell_units/README.md)。沿用已有 Conda／Isaac Sim 5.1；模型／策略依赖不随代码安装或创建项目虚拟环境。

新增仪器源包从 [assets/README.md](../../assets/README.md) 的固定 HF revision 获取，解压至 `local_assets/`；保留原 LabSim Franka 基础资源。HF 上仍为此前发布版本，未包含本轮 unit 结果、策略权重和最新 HTML。

本轮更新本地工程、统一 HTML、中文 MD 及自动生成代码快照，并按授权推送代码分支、创建 PR；不更新 HF。快照不含模型、媒体、H5、环境或 .git；保留资产下载说明。原 RM65 等本地工作保留，但不属于本次 unit 改动的审查范围。
