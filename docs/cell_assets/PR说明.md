# 单细胞前流程数字资产 API、Franka 交互与 HF 交付

已提交：[PR #1](https://github.com/zez2001/LabSim/pull/1)，等待项目负责人评审，未合并。

## 解决的问题与最终行为

前九类设备缺少统一的资产获取、Isaac 适配及可追溯交互入口。本改动注册 7 个固定来源条目（6 类主资产及 1 项辅助支架），通过 `list_assets`、`get_asset`、`fetch_asset`、`convert_asset`、`load_asset` 获取、校验、转换和加载。九类清单、替代关系与阻塞集中在 `config/cell_assets/coverage.json`。

提供三个已验证的 Franka 接触任务：IKA 开盖→装载→关盖、DIYNAFLUOR 取帽→停放→盖回、MagSep 空架体放入 Flex 工位后取回。OpenFlexure 取放尝试保留失败状态；PCR 仅支持机构回放；第 2、3、8 类整机仍缺资料。以上不代表移液、磁珠纯化、温控或浓度测量完成。

## 实现与验证

- 本分支：`codex/labsim_junjie_yao_20261027`，目标：`codex/labsim`；已同步集成基线 `abf7556`，保留上游 Project_v1／v1.1 更新。
- 复用 Franka 场景、连续 IK、相机与录像接口；任务参数独立配置，输出拒绝覆盖。判分检查双指接触、物体运动、实际释放、撤离、稳定和非预期碰撞。
- 新增设备及快照 CPU 检查已接入 GitHub Actions；新增轻量依赖 `trimesh==4.5.1`。
- 同步后执行 CPU workflow 的全部测试文件（分两批）：**847 passed、1 skipped**。其中资产与快照为 63 passed、1 skipped；跳过项是普通 Python 缺 `pxr`，不代表 GPU 验证。
- `git diff --check` 通过，7 个注册条目离线获取通过。新增变更只含源码、配置、测试和 Markdown，没有新增大型模型或媒体。
- 既有 GPU 证据：IKA 36/36；DIYNAFLUOR 32/32；Flex／MagSep 32/32、6120 步、约 51 秒。OpenFlexure 接近碰撞，未通过。本次同步与交付没有重跑 GPU 或真机。

复现 CPU：按 `.github/workflows/cpu-contracts.yml` 的 `contracts` 测试列表运行；资产单独检查：

```bash
python -m pytest -q -p no:cacheprovider tests/test_cell_assets.py tests/test_export_code_snapshot.py
```

复现设备操作需要 Python 3.11、Isaac Sim 5.1、GPU、原工程 Franka／场景资源以及 HF 仪器源包。完整命令见 [API 与 Demo](../../demos/cell_assets/README.md)。

## 资产与数据影响

新设备使用独立命名空间，不改写上游冻结场景、既有数据标签或历史证据。质量、摩擦及布局仍有未标定假设；未做真机和现场测量。

大型资产、40 段 MP4、单文件 HTML 和仿真证据位于 [HF 公开仓库 PercyM/labsim-cell-assets](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/f6b0f9f2dbe5046c0833fb099121e5a551d208f7)。固定 revision：`f6b0f9f2dbe5046c0833fb099121e5a551d208f7`，53 个发布文件均已回读核对大小和 SHA256；2026-10-27 已改为 Public，下载无需登录或申请权限。各来源许可单独保留，代码许可不覆盖模型。

[`assets/README.md`](../../assets/README.md) 保留为普通 Git 文本下载入口。HF 源包解压至 `local_assets/`，调用 `fetch_asset(..., offline=True)`；默认在线源仍是目录中固定的上游来源，未实现自动从 HF 镜像下载。原 LabSim 基础资源需保留，HF 新仪器包不包含其全部内容。

## 交接

- [数字资产交接汇报](交接汇报.md)：九类对应、成功／失败边界和未完成项。
- [资产下载与调用](HuggingFace上传指南.md)、[来源与许可](来源与调研.md)。
- [代码交付说明](../../DELIVERY.md)：唯一完整本地工程、最终结果和可重复导出的轻量代码副本。
- HF 的 `assets/` 存模型包，`videos/` 存独立 MP4，`showcase/` 存 HTML，`evidence/` 存执行记录。

通过 PR 交由负责人审核；不自动合并集成分支。
