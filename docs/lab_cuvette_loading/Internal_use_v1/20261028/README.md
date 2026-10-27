# Internal_use_v1：文档与内部使用体验

日期：2026-10-28。当前版本 `Project_release_v1`，HF资产沿用 `bb880f098180c291f6f65995f969d48047207067`。

正常使用从[主页](../../../../README.md)或[组内指南](../../../development/ONBOARDING.md)开始。本目录保存本次修改与验证证据；历史报告、任务标签和源资产保持原样。

## 修改范围

- 项目主页和组内使用顺序：准备环境、完整Teacher、标准示范、ACT/DP读取、策略接入。
- 当前版本快捷别名 `current`、启动身份摘要及显式 `record_purpose`。
- 用途集合与资格分离、历史哈希绑定sidecar、数据依赖检查与copy移交。
- 公开图像/H5/模型processor三层契约，实际部署tokenizer本地审计，后续服务只读输入审计。

本次保持场景、资产尺寸、质量/摩擦、物理步进、控制器、动作转换数值和成功判据。

## 验证证据

- [历史数据用途、移交及标签保护](data_usage/README.md)：π0.5正式评测1条，诊断11条，探针10条；生命周期资格2/1/3；14个原H5及标签保持。
- [实际部署输入审计](../../Project_release_v1/internal_use/20261028/input_audit/README.md)：69份真实输入；首末tokenizer/processor本地重建；264→200截断；H5/模型图像分支对齐。
- 普通Teacher完整标准任务：运行代码 `5c6b6422f9ba6fc16ac7b4374799c5ed7e426e47`；结果在本次闭合验收后补充。

## 文档分类

当前使用指南：[README](../../../../README.md)、[ONBOARDING](../../../development/ONBOARDING.md)、[release技术参考](../../Project_release_v1/README.md)、[数据使用](../../Project_release_v1/data_usage.md)、[策略契约](../../Project_release_v1/external_policy/contract.md)。

技术参考：当前配置、资产锁、公开动作/回执契约、数据用途与资格定义。历史验收：各版本的validation、生命周期实测、策略原始输入及评分记录；按原运行身份引用。

`previous_guides/`保留修改前文档原文字节，用于审查差异。副本的相对链接按原文件在仓库的位置解释，当前导航不进入这些副本。原仓库提交为`5a23c2a919de51bd6c3e19d6498dbd543a1b73ee`。
