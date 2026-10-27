---
language:
- zh
- en
tags:
- robotics
- simulation
- isaac-sim
- laboratory
- digital-assets
license: other
license_name: mixed-third-party-licenses
license_link: https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/LICENSE
---

# LabSim 实验室数字资产与机械臂演示

**要使用三维数字资产，下载下面的「完整资产包」即可。** 视频和 HTML 是演示资料，不是模型文件。

| 你想做什么 | 点击这里 | 说明 |
| --- | --- | --- |
| **下载全部数字资产** | **[下载完整资产包 · 71.3 MB](https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/main/assets/LabSim-digital-assets.zip?download=true)** | 包含全部 **7 个注册资产** 的 307 个源文件、纹理、装配资料与许可证。解压后供 LabSim / Isaac Sim 5.1 转换加载。 |
| 看所有设备和机械臂演示 | [下载整合展示页 · 64.4 MB](https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/main/showcase/LabSim%E6%95%B0%E5%AD%97%E8%B5%84%E4%BA%A7%E4%B8%8E%E6%9C%BA%E6%A2%B0%E8%87%82%E6%BC%94%E7%A4%BA.html?download=true) | 下载 HTML 后用浏览器打开，40 段视频已内嵌，无需另下 MP4。 |
| 单独看或下载 MP4 | [进入视频目录与索引](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/main/videos) | 按 19 个演示任务分文件夹，共 40 段视频，含正面、侧面及部分细节视角。 |
| 查看判分和执行记录 | [下载仿真证据包](https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/main/evidence/simulation-evidence.zip?download=true) | 结果 JSON、必要轨迹及规划记录；用于复核演示结果。 |

> 当前仓库为 **Public（公开、无访问审批）**，成员和其他访问者均可免登录下载。资产包是源模型集合，不是开箱即用的完整动态 USD 场景；还需要本轮 LabSim 源码和配置。

## 资产包里有哪些设备？

按设备需求表顺序列出。三类缺失整机没有放入占位模型，也不计入资产数量。

| 序号 | 需求类别 | 包内实际资产 | 已验证范围或缺口 |
| --- | --- | --- | --- |
| 1 | 自动细胞计数仪 | OpenFlexure Cell Counter 打印件装配 | 静态可加载；机械臂计数室取放未通过，夹指与支座碰撞，需要合适夹具。 |
| 2 | 液滴微流控单细胞处理设备 | 无整机；Poseidon 仅为辅助显微镜支架 | 缺合格整机装配与接口资料，辅助支架不替代整机。 |
| 3 | 微孔单细胞处理设备 | 暂缺 | 缺可信分件、尺寸及完整装配资料。 |
| 4 | 全自动液体处理工作站 | Opentrons Flex | Franka 装载／取回 MagSep 空架体通过；未验证移液。 |
| 5 | PCR 热循环仪 | Bio-Rad CFX Opus 96 | 仅机构回放；缺可信孔腔碰撞和匹配耗材，不能用于插管／装板。 |
| 6 | 磁珠纯化模块 | MagSep 12 管架体 | 空架体抓取、搬运、放置和取回通过；未模拟磁珠纯化。 |
| 7 | 温控／混匀反应模块 | IKA KS 4000 i control | Franka 开盖→装载烧杯→关盖通过；未模拟温控／混匀过程。 |
| 8 | 核酸片段分析仪 | 暂缺 | 缺满足要求的整机 CAD 与正确机构资料。 |
| 9 | 核酸浓度检测仪 | DIYNAFLUOR 打印件装配 | 取帽→停放→重新抓取→盖回通过；未模拟浓度测量。 |

共 6 类主资产和 1 项辅助支架，即 7 个注册条目。设备型号、替代关系和来源见 [完整覆盖清单](https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/metadata/coverage.json)；各资产 ID、源版本和转换参数见 [资产注册表](https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/metadata/catalog.json)。

## 先看这三段机械臂流程

- [IKA：完整开盖、装载、关盖](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/main/videos/full)。
- [DIYNAFLUOR：取帽、停放、盖回](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/main/videos/cap-cycle)。
- [Flex × MagSep：架体装载和取回](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/main/videos/rack-loading)。

这三条是固定场景下通过检查的接触流程；其余视频包含早期版本、失败尝试和仅关节回放，见 [视频状态索引](https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/videos/README.md)。

## 下载后怎么用？

1. 下载 **`assets/LabSim-digital-assets.zip`**，解压到一个独立的资产缓存目录，例如 `~/LabSim-hf-assets/`。目录内应直接出现 `chemlab/`、`magsep/`、`diynafluor/`、`openflexure_counter/`、`poseidon/`。
2. 沿用现有 LabSim / Isaac Sim 5.1 环境，将 `LABSIM_ASSET_CACHE` 设置为上述解压根目录。
3. 在本轮 LabSim 源码中使用 `fetch_asset(asset_id, offline=True)` 校验和定位模型；启动 Isaac Sim 后调用 `convert_asset()`、`load_asset()`。详细示例和源文件校验见 [资产使用说明](https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/assets/README.md)。

代码项目：[zez2001/LabSim](https://github.com/zez2001/LabSim)。本轮源码已上传至 [功能分支 codex/labsim_junjie_yao_20261027](https://github.com/zez2001/LabSim/tree/codex/labsim_junjie_yao_20261027)，见 [PR #1](https://github.com/zez2001/LabSim/pull/1)，尚未合并到集成分支。仅下载模型不能自动运行气弹簧、动态帽子和装载流程。

## 仓库目录

```text
assets/       完整数字资产 ZIP 与使用说明（需要模型就下载这里）
videos/       按任务整理的 MP4、成功／失败／关节回放索引
showcase/     单文件 HTML，内嵌所有视频和资产截图
evidence/     仿真结果与轨迹证据 ZIP
metadata/     资产清单、设备对应、视频索引及 SHA256
docs/        来源、许可与适配限制
```

## Licenses

本集合复用 ChemLab、MagSep、DIYNAFLUOR、OpenFlexure 和 Poseidon 的开源模型。不同资产分别适用 CC BY-NC 4.0、CC BY-SA 4.0、GPL v3、CERN-OHL-S、BSD-2-Clause 等许可，**不能统一按 MIT 使用**；公开下载不改变原许可义务。详见 [原始来源与许可](https://huggingface.co/datasets/PercyM/labsim-cell-assets/blob/main/docs/SOURCES_AND_LICENSES.md)，资产包保留原始声明和对应源文件。

所有通过结论来自固定布局仿真；质量、摩擦和布局未实物标定，没有真机或完整生化实验验证，也不代表厂商 CAD 或 NVIDIA SimReady 认证。目录整理不改变资产或视频内容，不产生新的 GPU 验证结论。
