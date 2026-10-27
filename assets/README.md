# 数字资产获取说明

代码交付版保留本目录作为资产入口，大型模型通过 Hugging Face 获取。

- **下载：[完整仪器资产包（约 71.3 MB）](https://huggingface.co/datasets/PercyM/labsim-cell-assets/resolve/f6b0f9f2dbe5046c0833fb099121e5a551d208f7/assets/LabSim-digital-assets.zip?download=true)**，包含 7 个注册资产的模型、纹理、装配源文件和许可证。
- **固定版本：**`f6b0f9f2dbe5046c0833fb099121e5a551d208f7`。仓库为 Private，需有访问权限并登录。
- **解压位置：**工程根目录的 `local_assets/`，内层直接包含 `chemlab/`、`magsep/`、`diynafluor/`、`openflexure_counter/`、`poseidon/`。这是加载 API 的默认缓存位置；其他位置可通过 `LABSIM_ASSET_CACHE` 指定。
- **加载方式：**在 LabSim / Isaac Sim 5.1 环境中调用 `fetch_asset(..., offline=True)`，再转换、加载；完整步骤见 [资产下载与调用指南](../docs/cell_assets/HuggingFace上传指南.md)。
- **基础依赖：**上述 HF 包是新增仪器集合，不包含原工程全部 Franka、房间及场景资源；这些资源需保留原 LabSim 基线的 `assets/` 内容。代码交付副本省略模型文件，不代表应删除基线资源。

模型沿用各来源许可证；静态加载、机构回放与机械臂接触验证的范围见 [交接汇报](../docs/cell_assets/交接汇报.md)。
