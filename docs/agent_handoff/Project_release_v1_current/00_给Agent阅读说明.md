# LabSim 环境发布：本轮技术反馈包

生成时间：{{GENERATED_AT}}；分支：`{{BRANCH}}`；交付提交：`{{SOURCE_COMMIT}}`。

[实际发布状态](发布信息.json)记录打包前查到的远端 SHA、GitHub 默认分支、首页 blob 和对应 CI；该收据在最终推送后查询生成，不能用计划状态替代。

完整工程：[本包对应固定提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。这是 `Project_release_v1` 本轮改动与结果的核查包；源码为必要变更子集，不是完整安装工程。Isaac 环境、策略权重、凭据及多 GB 轨迹未捆绑。大数据出处、大小、SHA256、获取与读取方式见下文。

本轮已完成有限长度的环境发布验收：同一 Isaac 进程连续成功→有效提前结束→reset 后成功；真实 π0.5 通过正式 RPC 持续交互，并在实际安全碰撞后保存有效失败；终止诊断、事务闭合和正常 ACT/DP 读取均有闭合证据。**长期常驻内存稳定性尚未证明，SDK 退出回调仍有已定位的错误。** 策略未完成装载不等于环境执行失败。

## 阅读顺序与关键证据

1. [环境验收报告](docs/lab_cuvette_loading/Project_release_v1/release_acceptance.md)：冻结范围、准确运行命令、实际结果、修复和遗留项。
2. [发布版使用入口](docs/lab_cuvette_loading/Project_release_v1/README.md)、[生命周期与事务闭合](docs/lab_cuvette_loading/Project_release_v1/lifecycle.md)、[π0.5 契约](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。包根同有 `README.md`、`README_CN.md`、`README_EN.md`。
3. [同进程三集闭合审计](docs/lab_cuvette_loading/Project_release_v1/validation/same_process_collect_01_closed/summary.json)：同 PID 三集结果为成功、有效提前结束、成功，7539 / 180 / 7539 条 transition；120 个唯一 H5 对象全读，gzip、reset、UUID 和 finalization 对应关系已核查。
4. [正式 clean reader](docs/lab_cuvette_loading/Project_release_v1/validation/official_dataset_check_clean_4a71635/summary.json)：修复 release 条件组资格白名单后，正常 ACT/DP 均为 success=2、failure=1、all_valid=3。[首次正式 CLI 失败](docs/lab_cuvette_loading/Project_release_v1/validation/official_dataset_check/initial_cli_failure_observed.json)也保留。早先底层 generic reader 的 42 项检查不是正式资格检查，不与正式通过证据混写。
5. [真实模型全链路审计](docs/lab_cuvette_loading/Project_release_v1/external_policy/pi05_standard_01_closed_audit/summary.json)：实际 69 次推理、341 个动作、1021 个控制周期、17.0167 秒动作仿真，因 SAFETY_COLLISION 自然停止；不是计划上限 80/400/20 秒。原模型输入与输出、适配动作、实际 9D 命令、后继观察及暂停时钟均有对应记录。首末 `.npz/.npy`、完整客户端 `policy_events.jsonl`、模型/客户端进程退出记录在包内。
6. [π0.5 数据审计](docs/lab_cuvette_loading/Project_release_v1/validation/pi05_standard_01_env_closed/summary.json)及[专用索引说明](docs/lab_cuvette_loading/Project_release_v1/validation/pi05_standard_01_env_closed/curated_index_manifest.json)：**真实策略评测只有 episode_0000 一集**。episode_0001–0010 是同进程追加的 10 个 0.05 秒 reset 资源探针，不是 10 条策略失败。正式 clean CLI 的 failure/all_valid 各读 1 集，原始回执在 `validation/official_pi05_dataset_check_clean_4a71635/`。
7. [五种终止诊断](docs/lab_cuvette_loading/Project_release_v1/validation/termination_cases_01_closed/summary.json)及[权威资格字段补充核查](docs/lab_cuvette_loading/Project_release_v1/validation/termination_cases_01_closed/authoritative_fields_addendum.json)：145 项加 35 项通过。service_timeout 与 user_interrupt 是受控异常注入，task_success=null、record_valid=false，不能计作有效任务失败或训练样本。
8. [同口径性能与体积对比](docs/lab_cuvette_loading/Project_release_v1/validation/baseline_vs_collect_01_comparison/summary.json)：完整 episode 体积减少约 39.99%，physics+contact 存储减少约 85.10%；无损压缩且在线采样不变。第三集 rollout 比第一集慢，不能承诺稳定提速。RSS 增长尚未解释，FD 与采样 VRAM 的恢复不能替代长期内存稳定性证明。
9. [退出错误实际审计](docs/lab_cuvette_loading/Project_release_v1/validation/gui_finish_02_shutdown_actual_20261027/receipt.json)及[headless 范围补充](docs/lab_cuvette_loading/Project_release_v1/validation/gui_finish_02_shutdown_actual_20261027/headless_scope_addendum.json)：旧菜单 `get_stage_state` 异常未再复现，但 SDK `ManipulatorFactory` NameError 仍存在；进程退出 0 不能写成日志完全无错误。
10. [四页组会 DOCX](组会材料/LabSim_环境与评测进展_20261028.docx)、[完整 teacher 视频](组会材料/teacher_full.mp4)、[π0.5 实际安全停止视频](组会材料/pi05_collision.mp4)。三件材料同目录，DOCX 相对视频链接可直接打开；两条录像为本轮真实连续原文件的逐字节复制，无拼接或调速。[制作核查](docs/lab_cuvette_loading/Project_release_v1/meeting_source/meeting_final_media_QA.json)记录来源、hash、解码、迁移链接和逐页渲染检查。DOCX 声明宋体/黑体/Arial；QA 主机缺这些字体时用了已有 fallback，不声称本机已安装或再分发这些字体。

## 版本、配置与数据语义

物理场景仍为固定 standard：10×10×67.5 mm 假设尺寸、20 g 假设质量、原 A 座 `candidate_far_hinge`、单台仪器及完整白色 6×6 架。原座、接触配置、控制增益和评分门槛保持不变。本轮不训练、不采 random、不新增付费 GPT 调用，不宣称真实仪器标定或微米级现实精度。

物理与真实策略实际运行提交为 `122c4c03586abdfa7e3117c13e62f8d46f786b04`；五类终止 CLI 为 `73b1a9db9470f9706a3068a8ce24e7e09d8cfc65`；正式 reader 修复与 clean 读取为 `4a716359376de0132cc83cba3e5c7d27c791069e`。最终交付提交由包根 `文件清单.json` 的 source_commit 决定，不把较晚文档提交冒称全部物理运行提交。资产固定为 HF revision `bb880f098180c291f6f65995f969d48047207067`，本轮没有新资产发布。[实际环境依赖](docs/lab_cuvette_loading/Project_release_v1/validation/runtime_environment.json)、[83 项资产核对](docs/lab_cuvette_loading/Project_release_v1/validation/fresh_assets/manifest.json)及 CI/远端实际查询随技术证据保留。

`outputs/lab_cuvette_loading/Project_release_v1/` 只选入关闭后的原始小型配置、reset、结果、独立评分、完成标记和退出记录。最终 H5 attrs、task_properties.labels、qualification_json、collector/task 最终结果、标记及索引中的资格必须一致；早期 independent_score 是关闭前物理评分快照，完整性可为 pending/null，不是最终资格。原始记录没有事后改标签。

`config/`、`demos/lab_cuvette_project_release_v1/`、`tasks/`、`data_collectors/`、`policy/`、`policy_backends/`、`scripts/` 和 `tests/` 提供必要的发布配置、源码与测试。完整旧核心及第三方依赖从固定 GitHub 工程获取。`*_CPU_*attempt*` 的不完整审计副本未当作主证据打包，原 Git 历史仍保留；首轮正式 CLI 的真实资格错误单独保留，不能把它隐藏成从未失败。

## 大数据出处、获取与正常读取

[外部数据出处清单](docs/agent_handoff/Project_release_v1_current/external_data_sources.json)提供实际 H5、录像、physics/contact/execution 日志的本机路径、大小、SHA256 和闭合审计来源。该 JSON **不是下载服务**；本机绝对路径只是出处。接收者需向项目所有者索取完整 collection 目录，或按照固定代码和资产版本复现。HF 固定 revision 分发场景资产，不代表分发本轮全部原始轨迹；模型权重也未打包或重新下载。

**所有 `.h5` / `.hdf5` 均不在包内，包括 6KB 的 relative-link 索引。** 包内 `readonly_episode_index.index.json` / `index_build_receipt.json` 记录真实构建与筛选结果，其 index/source 字段指向原机器数据，不能直接据此读取 batch。拿到完整三集 collection 后，可在完整仓库中重建新索引；输出路径必须不存在：

```bash
python -m demos.lab_cuvette_project_release_v1.dataset_index /path/to/closed_collection \
  --output /path/to/NEW_release_index.hdf5 --mode relative-links
./labsim dataset-check --index /path/to/NEW_release_index.hdf5 \
  --sample-filter all_valid --policy both --output /path/to/NEW_reader_receipt.json
```

`relative-links` 要与所有来源 H5 一起移动；需单文件自包含时显式使用 `--mode copy`，会复制完整大数据。真实 π0.5 评测请按专用 curated_index_manifest 只选择 episode_0000，不能对整个 11 集 RPC 目录重建索引后声称 11 次模型失败。

报告内未复制的仓库链接由打包脚本固定到交付 Git 提交；原始 JSON/YAML 的本机路径保持原样用于追溯。原始收据的文件 hash 针对原文件，包内 Markdown 如因链接转换发生 hash 变化，可同时查文件清单中的 source_sha256 与 sha256。

## 传输核对与剩余工作

包根 `文件清单.json` 记录真实交付提交、各源文件与复制件 SHA256、大小和链接转换；`SHA256SUMS.txt` 供传输后核对：

```bash
sha256sum --check SHA256SUMS.txt
```

[清单准备记录](docs/agent_handoff/Project_release_v1_current/package_readiness.json)是打包前快照；最终提交与实际复制状态以包根生成记录为准。本轮仍需后续处理 SDK 退出回调、长程 RSS 增长归属、第二台机器复现及真实参数标定。已完成的有限长度验收不能扩大表述为无限期常驻稳定。

另有独立的 `LabSim_组会汇报包_20261028.zip`，严格只含一个 DOCX 和两条视频；本技术包承担完整核查材料，不应与组会 ZIP 的文件范围混淆。
