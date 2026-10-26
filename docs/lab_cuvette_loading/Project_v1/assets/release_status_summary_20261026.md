# Project_v1 公开发布核查摘要

核查时间：2026-10-26T11:30:51.077892+00:00。仅检查公开元数据、两个小型清单及代表文件 HEAD；没有重新下载资产/H5、上传文件、读取凭据或使用模型 API key。

HF Dataset：[Txie000/SLAI-Labsim](https://huggingface.co/datasets/Txie000/SLAI-Labsim) 当前为公开。观察到远端最新提交 `82317fe33089aca5a20827da2adc592a1e0fdddc`。运行时继续使用固定 revision，不跟随 main。

## 资产与代码索引

资产固定于 `bb880f098180c291f6f65995f969d48047207067`，路径 `releases/Project_v1_portable/`。代码入口 `config/lab_cuvette_loading/Project_v1/assets.lock.json`；清单 SHA256 `054bcdd8fff283a877fc2e2da897e55aaa53bc63935cdca1f3c2504b68e03beb`。远端发布 manifest 的 SHA256 与代码索引记录完全一致；82 个 HF payload 的路径、字节数、记录哈希均与发布清单一致。HF 另外保存1个发布清单。共有35个独立尺寸变体，默认 `cuvette_xy_1000`。

HF payload 共21,892,205字节；另有1个固定 Git LFS Franka依赖，10,063,498字节。HF单仓库不包含全部运行依赖；HF与固定 Git LFS合起来可公开下载当前任务全部83项依赖，无需作者私有路径。此前匿名空缓存83项/31,955,703字节完整下载、离线复用与安装均已通过，本轮直接复用该证据，不重复大文件下载。

生产入口 `runtime.resolve_config` 已在CPU上读取既有匿名下载资产，逐一通过35个注册ID的USD、源文件、sidecar及注册哈希校验；默认10 mm资产实际解析SHA为 `cd2ef00254241c7ba09c8a90da646da4a6d629bb41ddec4d754f2ebb6aa27537`。历史YAML中的原文件哈希不回写；生产解析器按公开注册记录原子更新路径、器皿/对照源文件哈希和注册表哈希。该读取核查不替代几何、烹饪碰撞或物理任务验证。

## 可读取的小型完整样例

样例固定于 `82317fe33089aca5a20827da2adc592a1e0fdddc`，路径 `examples/Project_v1_teacher_gui_01/`；代码索引 `config/lab_cuvette_loading/Project_v1/public_samples.json`。5个文件共283,927,640字节，公开树中的路径和大小与索引一致，远端小型样例清单 SHA256通过核对。代表H5 HEAD匿名访问成功。

H5保留完整6,348条观测—动作转换、双视角、状态、时间戳、事件和标签，只将两路策略RGB从256×256缩为96×96；没有截断时间或降帧。原始采集相机元数据保留，缩放变换单列声明。此前从空目录匿名下载后，正常 `./labsim dataset-check --sample-filter success --policy both` 已读出ACT和DP batch。未执行模型训练。

该GUI教师记录源代码为 `d09c5ffce2018702702eb0d4c77d862f1eae6faa`，场景指纹为 `75d288fe67e88c749cb578f36f3c246664b3e26d8455926bffbccf3576964de6`。它是独立早期快照，成功/有效标签原样保留；不得与后续正式重复测试默认混为同一配置。样例提交晚于资产提交是有意安排，两个版本分别锁定；代码中资产 revision 仍一致。

## 权利和许可边界

2026-10-26项目所有者已直接确认拥有相应权利，并明确允许公开原器皿/仪器CAD USD及派生版本。答复事实记录于 `license_and_dependency_audit.json` 的 `CAD_publication_permission`。采用 `LicenseRef-LabSim-UserAuthorizedCADRedistribution`，不把此确认写成厂家许可，也不把CAD资产笼统归为代码MIT。原始压缩附件、私人消息和凭据未上传。

自建参数化来源架及项目数值元数据采用MIT。Franka原USD的逐文件许可尚未核实，因此未重新分发至HF；本轮远端资产树也没有Franka/robots文件。下载器只从既有公开项目的固定Git LFS提交获取同SHA文件，下载可用性不等于许可已确认。

## 核查边界

本轮是公开状态和版本一致性复核。全量字节正确性的证据来自先前已保存的匿名下载及读取报告，不宣称本轮再次完成全量下载。公开发布不代表实物校准、真实精度验证或策略完整任务成功。

详细机器可读结果见同目录 `release_status_summary_20261026.json`；原始证据位于 `anonymous_download_summary.json`、`license_and_dependency_audit.json`、`../data/public_sample_anonymous_verification.json`。
