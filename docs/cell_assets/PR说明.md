# PR 草稿：单细胞前流程资产接入与 Franka 接触验证

状态：本地草稿，尚未提交、推送或创建 PR。当前功能分支 `codex/cell-assets-junjie-20261025`；预期向 `codex/labsim` 提交评审，须在后续获准提交时核对集成状态。

## 问题与结果

清单前九类设备缺少统一的源资产获取、Isaac 适配和可追溯交互证据。本改动注册 7 个固定来源条目，覆盖 6 类主资产及 1 项辅助支架，提供源文件校验、转换和加载 API；第 2、3、8 类仍明确待补资料，不创建占位整机。

已有 Franka 接触流程分别验证 IKA 开盖／装载／关盖、DIYNAFLUOR 遮光帽取放，以及 MagSep 空架体放到 Flex 工位后取回。OpenFlexure 原装夹爪接近碰撞，保持未通过状态。接触子任务不代表移液、磁珠纯化、温控或浓度测量已完成。

## 实现与交接

- 源资产及许可保存在项目外；Git 变更仅含代码、JSON、测试和中文 Markdown。
- 来源及固定版本集中在 `config/cell_assets/catalog.json`，九类对应与能力边界在 `coverage.json`。
- 复用既有 Franka 场景、连续 IK、相机和录像接口；任务参数集中配置，拒绝覆盖已有输出。
- 独立检查双指接触、实际物体运动、释放撤离、稳定和碰撞；未用附着或瞬移制造成功。
- 单文件 HTML 集中 19 次运行和 40 段录像；当前交接、API、来源许可和 HF 发布步骤分别有中文文档。

## 验证

- CPU：`python -m pytest -q -p no:cacheprovider tests/test_cell_assets.py`，59 passed、1 skipped。普通 Python 缺 pxr 的跳过项不是 GPU 成功证据。
- GPU 已有：IKA 连续周期 36/36；DIYNAFLUOR 32/32；Flex／MagSep 32/32、6120 步、51 秒。
- 失败证据：OpenFlexure 接近碰撞，非零退出；不计入通过数量。
- 结果包 62 个原清单文件、源码哈希、19 条结果与 HTML 一致；7 个源条目离线校验通过。网页逻辑及新增视频完整解码检查已执行；未进行本轮浏览器自动渲染测试。
- 本次复核未重跑已通过物理场景，沿用其有日期和哈希的执行证据。

## 限制与待办

固定布局与质量、摩擦等参数未实物标定。三类整机、PCR 可插入结构、匹配试管、OpenFlexure 夹具仍有缺口。HF 私有镜像已发布（`PercyM/labsim-cell-assets`，固定 SHA `f6b0f9f2dbe5046c0833fb099121e5a551d208f7`），53 个文件的远端回读及 SHA256 校验通过；下载后的 GPU 验证和现场测量未执行。完整复现命令、源版本和验证范围见 `demos/cell_assets/README.md`、`docs/cell_assets/交接汇报.md`，不可将未提交代码描述为远端已发布。
