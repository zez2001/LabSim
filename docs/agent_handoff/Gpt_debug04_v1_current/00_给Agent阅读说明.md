# LabSim GPT debug04 恢复与标准场景评测：工程反馈包

先读 [RESULTS.md](RESULTS.md)，再分别打开[历史 debug04 的完整 Progress](cases/historical_debug04/progress/progress_report.html)和[本次正式集的完整 Progress](cases/formal_debug04_01/progress/progress_report.html)。本包用于核查策略身份、历史恢复方法、新基线执行、量化结果和证据链；详细 DOCX 与两条完整双视角录像另有精简汇报包。

## 两组记录分别统计

- **历史组**：原 `Project_v1_1/gpt_debug_04/episode_0000`，episode ID 为 `28bd2fc2-7bd7-44ee-9fb6-aaff53cbc99d`，原运行提交为 `63410bf9258ba2f9bd0af4d517194523fca6617c`。本轮只读重分析其完整轨迹、模型输入和原始标签；历史原文件及身份不改写。该组只有一条历史记录。
- **新基线组**：在当前 `Project_release_v1 / standard` 场景使用精确恢复的 debug04 策略，实际执行提交为 `801a3f704298faf00cc31b55d572e5e0ff4bb4b6`。预声明计划为十集，本轮得到的新增授权覆盖其中一集；其余九集为 `unstarted_not_authorized`，没有对应的新运行记录。以逐集清单中的实际启动、关闭状态和原独立评分读取结果。
- 历史组不加入新组分母。历史 P9 GPT 与 π0.5 评测只作已有背景，固定入口见[此前评测结果](https://github.com/zez2001/LabSim/blob/9bdf8c7c36b0c324cb9009bfe9aa0538dd6ff485/docs/lab_cuvette_loading/Policy_eval_v1/RESULTS.md)，本包不重复复制该批媒体或数据。

两条原独立评分均未完成完整装载：历史记录原失败类型为 `GRASP_SLIP`，本次新记录为 `BLOCKED`、`POLICY_FINISH_REQUEST`。新记录已正常关闭，记录完整且有效，完整任务成功为 false；它可以通过原 failure reader 读取，不具备成功 BC 示范资格。阶段证据及有效插入指标见结果报告，不能以“有完整录像”代替任务成功。

## 阅读顺序和目录

1. [RESULTS.md](RESULTS.md)：本轮结果、阶段、终止原因、适用性、成本、运行及复算命令。是否完成插入、释放、撤离和稳定观察，以该文件及原独立 scorer 为准，不按录像名称或 Progress 历史锁存推断。
2. [策略身份说明](protocol/identity.md)、[机器可读身份](protocol/identity.json)、[环境对照](protocol/environment_comparison.md)：原配置、静态 instructions、通用工具、上下文轮数、图像编码、真实模型返回身份、输入隔离，以及当前环境与原运行的差异。
3. `config/lab_cuvette_loading/Gpt_debug04_v1/`：逐字恢复的 provider 配置和冻结协议。`protocol/` 同时保存实际执行协议及授权摘要来源；授权文件只含额度与身份，不含凭据。
4. `results/historical/` 和 `results/formal/`：两组各自的逐集 CSV/JSON、阶段结果、分析及计划项。N/A 或 null 表示未进入指标适用区间；未达成阶段不作为零秒成功耗时。
5. `cases/historical_debug04/` 和 `cases/formal_debug04_01/`：各自完整 Progress、完整双视角录像、侧／腕播放器媒体及来源凭据。HTML 的媒体和数据依赖按相对目录保留，可直接整目录传输。
6. `validation/`：源文件及标签保护、事件重放、运行闭合、输入、测试和其他实际生成的核验记录。运行状态、记录完整性与任务成功分别阅读。
7. `code/`：本轮独立 namespace、原策略 vendor、财务授权桥、启动器、分析工具及 CPU 测试。vendor 三个原文件逐字保留，来源 Git blob 和 SHA256 见 `source_manifest.json`。

## 执行与费用边界

新组采用标准固定场景、`cuvette_xy_1000`、内部 `candidate_far_hinge` A 座、240 Hz 物理和60 Hz 控制、170秒仿真上限、seed 0，关闭场景随机化。策略使用原 debug04 的 context4／640 high 双视角配置，不启用 P9 的 temporal、detail、active-view 或 self-state 扩展。完整 prompt、工具 schema 与静态任务文本的哈希见身份文件和冻结协议。

原共享账本保留377次网络尝试及估算费用 `$29.267746`。本轮授权新增最多 `$20`、480次网络尝试、正式一集；唯一派生累计账本的上限为 `$49.267746 / 857`。授权绑定唯一账本路径；失败、启动异常及预算终止均保留，不能更换账本重复获得同一额度。费用按返回 usage 和配置费率估算，实际平台账单以账户侧记录为准。最终用量由本次成本文件及发布核验记录给出。

本次实际使用42次调用／网络尝试，估算费用 `$3.44501`；旧377条前缀与原共享账本完全一致，唯一 trial 为 `debug04_01`。正常 ACT 与 DP 入口已读取实际 batch，原 H5、独立评分和完成标签在读取前后哈希一致，核验见 `validation/formal_audits/official_reader_summary.json` 与 `independent_funding_final.json`。

本包不含 API key、token、凭据文件、Isaac 环境、HF 资产实体、模型权重或大型 H5。H5、模型实际输入和原始接触记录保留在工程端；包内 JSON 提供原绝对身份、来源路径和哈希，供有权限的接手者定位。可运行完整工程从下面的固定提交获取；付费运行仍要求新的、明确绑定的授权，阅读报告与离线分析不触发模型调用。

## 传输及核对

完整双视角视频位于 `cases/*/*_dual.mp4`；每案 `media_receipt.json` 记录原视频 SHA256、尺寸、帧数、时长、显示转换与全片解码检查。没有拼接不同尝试，也没有用生成帧补齐操作。Progress 播放器无法定位时，可通过支持 HTTP Range 的本地静态服务器打开本包，并保持目录树不变。

`publication.json` 记录实际运行提交、最终发布提交和 CI；`protection_final.json` 记录历史、资产及本轮源文件保护。打包工具生成 `文件清单.json` 与 `SHA256SUMS.txt`，可在包根运行 `sha256sum --check SHA256SUMS.txt` 核对传输。若需要详细原数据，依据其中身份单独移交，不把派生阅读副本当作原始物理数据。

开发分支：{{BRANCH}}

最终发布提交：{{SOURCE_COMMIT}}

打包时间：{{GENERATED_AT}}

[固定提交完整源码](https://github.com/zez2001/LabSim/tree/{{SOURCE_COMMIT}})
