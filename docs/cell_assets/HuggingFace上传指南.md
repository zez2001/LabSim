# Hugging Face 发布与调用指南

更新：2026-10-27。**上传完成，53 个文件已从固定提交重新下载，大小与 SHA256 全部匹配。**

- 仓库：<https://huggingface.co/datasets/PercyM/labsim-cell-assets>，Dataset，**Public（公开、无访问审批）**，账号 PercyM。
- 固定资产版本：`f6b0f9f2dbe5046c0833fb099121e5a551d208f7`。
- 本次上传：53 个文件、187,100,920 字节（约 187 MB）；仓库另有自动维护的 `.gitattributes`，共 54 个文件。
- GitHub：代码已推送至 `codex/labsim_junjie_yao_20261027`，[PR #1](https://github.com/zez2001/LabSim/pull/1) 等待评审，未合并。
- 验证边界：完成文件回读校验；本轮没有重跑下载后的 GPU 仿真或真机验证。

## 下载入口与目录

- **要数字资产：[下载完整资产包](https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/main/assets/LabSim-digital-assets.zip?download=true)**，内含全部 7 个注册资产，无需下载视频即可获取模型。
- 视频统一在 [`videos/`](https://huggingface.co/datasets/PercyM/labsim-cell-assets/tree/main/videos)，按 19 个任务分文件夹；`videos/README.md` 提供成功／失败／仅回放状态及逐视角下载链接。
- `showcase/` 存整合 HTML，`evidence/` 存仿真证据，`metadata/` 存清单和哈希，`docs/` 存来源许可，`assets/README.md` 提供加载步骤。
- 原始模型、视频、证据和 HTML 字节保持不变；此轮只调整远端路径、说明和索引。旧路径仍可通过前一固定版本访问，默认入口使用本页的新版本。

## 内容

| 文件 | 用途 |
| --- | --- |
| `assets/LabSim-digital-assets.zip` | 7 个注册条目的 307 个源文件。保留五个来源目录、固定上游版本、网格、纹理、装配源包及原始许可。 |
| `videos/<run>/<view>.mp4` | 19 次运行的 40 段独立视频，与最终 HTML 内嵌 MP4 逐字节一致。 |
| `showcase/LabSim数字资产与机械臂演示.html` | 唯一整合展示页，下载后本地打开。Dataset 不直接托管 HTML 网站。 |
| `evidence/simulation-evidence.zip` | 对应结果、必要轨迹及规划证据。 |
| `README.md`、`LICENSE` | 数据集说明与混合许可声明；不将第三方资产统一重新授权为 MIT。 |
| `metadata/catalog.json`、`metadata/coverage.json` | 原始来源、固定版本、九类设备对应及能力边界。 |
| `metadata/asset-files.json`、`metadata/videos.json`、`metadata/upload-manifest.json` | 源文件、视频及上传文件的大小、SHA256 与结果索引。 |

成功任务、失败尝试、仅关节回放在 `metadata/videos.json` 和 HTML 中分别标明。视频和上传成功不能解释为全部设备可用、完整生化实验或实物标定。

本版是源资产镜像与演示证据，**不是预导出的完整动态 USD 场景包**。气弹簧、动态帽子和架体交互仍依赖本轮 LabSim 代码和配置；接手者需同时取得 GitHub 功能分支 `codex/labsim_junjie_yao_20261027` 的源码，发布状态见 [交接汇报](交接汇报.md)。

## 下载、解压和离线调用

沿用现有 `labsim` Conda 环境，不在项目内另建环境。仓库已公开，下载不需要 `hf auth login` 或 Token；示例使用 `token=False` 明确执行匿名下载。网络若需要代理，沿用本机已配置且可用的代理即可。

在本轮 LabSim 源码目录运行：

```python
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile
from huggingface_hub import hf_hub_download
from utils.cell_assets import list_assets, fetch_asset

repo_id = "PercyM/labsim-cell-assets"
revision = "f6b0f9f2dbe5046c0833fb099121e5a551d208f7"
archive = hf_hub_download(repo_id, "assets/LabSim-digital-assets.zip", repo_type="dataset", revision=revision, token=False)
manifest = hf_hub_download(repo_id, "metadata/asset-files.json", repo_type="dataset", revision=revision, token=False)
cache = Path("local_assets")
cache.mkdir(exist_ok=False)
with ZipFile(archive) as package:
    package.extractall(cache)
for item in json.loads(Path(manifest).read_text()):
    data = (cache / item["path"]).read_bytes()
    assert len(data) == item["bytes"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"]
os.environ["LABSIM_ASSET_CACHE"] = str(cache)
for asset in list_assets():
    print(asset["asset_id"], fetch_asset(asset["asset_id"], offline=True))
```

解压根目录应直接包含 `chemlab/`、`magsep/`、`diynafluor/`、`openflexure_counter/`、`poseidon/`。不能把 ZIP 直接交给 USD 加载器。`fetch_asset()` 默认上游来源未改写；镜像下载后使用离线模式，随后在启动 Isaac Sim 5.1 的环境内调用 `convert_asset()` 和 `load_asset()`。

GPU 复现示例（**这次发布后未重跑**，输出目录须尚不存在）：

```bash
export LABSIM_ASSET_CACHE="$PWD/local_assets"
python -m demos.cell_assets.preview --asset-id magsep_rack_12_tube --offline --output /new/path/hf-preview
python -m demos.cell_assets.handling --offline --output /new/path/hf-handling
```

已有本地仿真结果仍以交接汇报和各 `result.json` 为准；不要将文件校验替代物理验证。

## 执行记录与维护

网页整批提交曾遇到 `Failed to fetch`。改用终端后已成功登录，但数据集 README 的 `license_link` 使用相对路径，不符合 HF 元数据要求，导致上传器反复重试。已改成完整 HTTPS 许可证链接，并在恢复上传前通过 `DatasetCard.validate(repo_type="dataset")` 的服务端校验。保留原上传进度后补齐文件，最终对固定版本的全部 53 个文件完成回读校验。

发布证据见最终交付目录的 `HuggingFace发布记录.json`，含完整 SHA、逐文件校验值和验证范围。当前临时上传包、临时下载副本、临时脚本及“下载”快捷入口在核验完成后清理；最终 HTML、证据、源资产缓存和本机登录凭据保留。

以后修改 README 时仍需先进行服务端元数据校验；只更新所需文件，并在完成后记录新的固定提交及校验结果。原版发布 SHA 是不可变的复现入口。

## 许可和分享

ChemLab 模型 CC BY-NC 4.0、MagSep CC BY-SA 4.0、DIYNAFLUOR GPL v3、OpenFlexure 上游硬件 CERN-OHL-S-2.0 或 README 规定的后续版本／定制部件仓库 GPL v3、Poseidon BSD-2-Clause。原许可、署名与对应源文件随源包保留；公开下载不取消许可条件。

未发布未筛选的 `references/来源材料.zip`、整个工程、Conda、凭据或无关文件。仓库公开后，任何人均可通过链接下载。若将来只允许项目成员访问，可迁入团队 Organization 的私有数据集并授予成员读取权限；本轮按用户要求选择公开。

## 公开共享（2026-10-27）

已按用户要求改为 Public，未开启 gated 访问审批。公开说明版本为 `0eac1b793c889c20adbbdf6f684069f557add0b8`；仅更新首页、资产下载说明和上传清单。原固定资产版本 `f6b0f9f2dbe5046c0833fb099121e5a551d208f7` 继续可用，模型、视频和历史仿真证据未改动。

匿名验证已通过：不携带认证头完整下载资产 ZIP、代表 MP4 和更新后的三份说明／清单，大小与 SHA256 一致；新旧版本对象核对证明其余 51 个仓库文件未变。验证记录保存在本地 `results/final/HuggingFace发布记录.json`，不将本轮下载检查当作新增物理实验。
