# LabSim Env_v1 完成状态和正式入口

> 历史版本：**Env_v1**。以下原文的分支、当前状态及命令属于该版本验收时点。当前使用请从 [Project_release_v1](../Project_release_v1/README.md) 或 [组内指南](../../development/ONBOARDING.md) 开始。


当前分支 [`codex/lab-cuvette-env-v1`](https://github.com/zez2001/LabSim/tree/codex/lab-cuvette-env-v1)。这是正式任务集成版本，**完整原座装载仍未完成**。V0至demo04及全部历史输出保留，[阶段状态](../../../TASK_STATUS.md)持续更新；[机器可读完成矩阵](completion_matrix.json)分别记录已运行范围及限制。

本轮交付：[DOCX报告](results_20261021/LabSim_Env_v1_本轮进展报告.docx)、[Markdown及本地视频](results_20261021/LabSim_Env_v1_本轮进展报告.md)、[24条实际运行](results_20261021/actual_runs.csv)、[5次策略尝试](results_20261021/policy_attempts.csv)。报告8页逐页核查通过；完整便携H5与小阅读包分别保存。

## 完成范围

- 场景已实际加载：单仪器、打开盖板、腔内原A/B座、完整6×6架和用户名义12.5×12.5×67.5 mm器皿。视频估计布局、Franka代理及20 g假设均未真实校准。
- 相机真实projection及官方zero_delay修复已实际验证：fixed01的935/935观测匹配当前USD，最大位置残差6.67e−16 m；旧extract01的0.966282 mm保留为修复前记录，不再当最新未解决项。不等同真实光学校准。[新实证](data/extract_fixed01_inspection/renderer_USD_sync_audit.json)
- grasp_hold_04是架内承重稳定；extract01及固定姿态对照均滑移。continuous_latch01已实际清槽并搬运，独立抓持/搬运通过，最大相对漂移30.42 µm/0.0355°；3秒末段漂移230.445 µm超过原200 µm，整体false保留。[基线分析](data/extract01_control_analysis.json)与[固定姿态对照](data/extract_fixed01_control_comparison.json)
- π0.5、GPT-6 Astra direct、真实RPent Harness VLA均完成真实图像→模型→5动作→后继观测，每条仅0.25秒动作、task_success=false。这是接口接通，不是完整任务或性能评测。[三链证据](policy_evidence/real_three_chain_01.json)
- 新数据读取、时间/动作对齐、原格式便携导出及原minimal_pick真实回归通过。[数据验收](data/README.md)
- 真实RPC API的23项检查通过，包括6次reset、seed/装配复现、2秒暂停、动作持续时间、chunk、迟到拒绝和native门控0控制步；random仅初始化检查，不是任务批次。[API实证](policy_evidence/live_environment_api_validation.json)
- A/B原座必要入口仍阻塞所有直立yaw；原12.6 mm中央参考宽度不代表完整净空。[几何](geometry/README.md)

最新[preinsert_continuous_latch01](data/preinsert_continuous_latch01_result_summary.json)已真实通过：82.65秒、清槽抓持搬运、安全接近约1 mm、上抬超过8 mm、末1秒漂移0.4835 µm。它没有插入/松爪/实际撤离，full/native_pair仍null；原continuous01超限false保留。原座完整装载、释放后稳定、固定5次/random10次、20+20及策略正式批次仍未完成。Astra01/02排除保留。新raw getter仅CPU及保存metadata输入契约检查，尚未重启raw RPC实测；模型tool独立净化。

## 统一入口与采集门控

从工程根目录调用，复用现有`../labutopia-env/bin/python`。GUI为默认模式；加`--headless`关闭窗口。输出必须使用不存在的新目录；单GPU顺序运行Isaac。以下CLI基于已使用的正式入口，示例新批次并未自动运行。

预览和静止抓持功能已实际运行：

```bash
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode preview \
 --env-config config/lab_cuvette_loading/Env_v1/grasp_hold.yaml \
 --headless --output outputs/lab_cuvette_loading/Env_v1/manual_preview_01

OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode teacher --subtask grasp_hold \
 --env-config config/lab_cuvette_loading/Env_v1/grasp_hold.yaml \
 --headless --output outputs/lab_cuvette_loading/Env_v1/manual_grasp_hold_01
```

完整standard/random调用存在，但**当前原座几何门控会停止loading；正式批次尚未运行**。完整流程通过前不扩量，random保持仪器与内部座、架体与槽位一起变换。预检停止不算物理插入失败：

```bash
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode teacher --subtask loading \
 --layout-mode standard --seed 0 --episodes 1 --headless \
 --output outputs/lab_cuvette_loading/Env_v1/manual_loading_standard_01

OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode teacher --subtask loading \
 --layout-mode random --seed 7000 --episodes 1 --headless \
 --output outputs/lab_cuvette_loading/Env_v1/manual_loading_random_01
```

单独几何审计：`bash demos/lab_cuvette_env_v1/run.sh --mode audit --output <新目录>`。启动和reset检查当前输入绑定；过期缓存自动重算，不复用历史布尔值。

## 正常读取与视频回看

ACT/DP普通读取已实测。诊断成功可按`all_valid`读取，不能进入完整loading成功BC。`success`/`failure`仅选择对应资格的完整任务；当前没有足够完整装载样本，不能改标签制造batch。

```bash
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 outputs/lab_cuvette_loading/Env_v1/grasp_hold_04/episode_0000/dataset/episode_0000.h5 \
 --sample-filter all_valid --policy-type act

../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 outputs/lab_cuvette_loading/Env_v1/grasp_hold_04/episode_0000/dataset/episode_0000.h5 \
 --sample-filter all_valid --policy-type dp --n-obs-steps 3

# 对未来含合格完整loading结果的索引筛选，不代表当前已有这些数据
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 COMPLETE_LOADING_INDEX.hdf5 --sample-filter success --policy-type act
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 COMPLETE_LOADING_INDEX.hdf5 --sample-filter failure --policy-type act

xdg-open outputs/lab_cuvette_loading/Env_v1/grasp_hold_04/episode_0000/dual_view.mp4
xdg-open outputs/lab_cuvette_loading/Env_v1/extract_transport_01/episode_0000/dual_view.mp4
```

视频文件实际存在；单独side/wrist录像与JSONL/H5在同一episode目录。main真实动作回放另已验收15个控制周期，执行关节/夹指命令逐行相同、exit0，新独立结果仍false。这只是0.25秒短诊断回放，不是完整装载重放或全状态确定性保证；准确命令见[回放入口与范围](replay_README.md)，[实际证据](data/replay_astra03_01_actual_summary.json)。

本轮[阅读版媒体来源](data/reading_media_provenance.json)包含同一次82.65秒安全预插入诊断的连续主录像、提取滑移失败全程和腕部关键片段。整段压缩保留原分辨率、fps和全部帧，关键片段按声明时间裁剪，原录像均保留；没有拼接成完整loading。

## 便携原格式导出

preview04已实际导出并验证原H5字节、链接及正常ACT/DP读取。下面是已验证CLI的新目标示例；不修改动作、fps或标签，不表示LeRobot/OpenPI转换完成。大H5不放进精简阅读包。

最新安全诊断成功数据也已原格式便携导出，2546460010字节，无H5外链，正常ACT/DP all_valid读取通过；[实际导出清单](data/preinsert01_portable_export_validation.json)。它是诊断成功，不进入完整loading成功BC，也不放入小阅读包。

```bash
../labutopia-env/bin/python scripts/export_lab_cuvette_env_v1_episode.py \
 outputs/lab_cuvette_loading/Env_v1/preview_04/episode_0000 \
 --output outputs/lab_cuvette_loading/Env_v1/portable_samples/manual_preview04_01 \
 --manifest-copy outputs/lab_cuvette_loading/Env_v1/manual_portable_export_01.json
```

## RPC环境与三个后端

只运行一个环境服务，已有8097端口服务时复用。模型等待不推进物理，真实动作才步进：

```bash
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode serve --subtask preinsert_diagnostic \
 --env-config config/lab_cuvette_loading/Env_v1/preinsert.yaml --port 8097 \
 --headless --output outputs/lab_cuvette_loading/Env_v1/manual_rpc_01
```

π0.5/Harness使用本机已有RPent与checkpoint，服务在线时不重复加载。以下基于本轮真实调用CLI，输出目录换新。checkpoint、版本、动作语义与全部尝试见[后端说明](policy_backends.md)。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 ../rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.pi05_server \
 --model-path ../rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT \
 --host 127.0.0.1 --port 8098 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/manual_pi05_service_01

../rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend pi05 --policy-config config/lab_cuvette_loading/Env_v1/policies/pi05_libero.yaml \
 --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 0 \
 --max-model-requests 1 --max-actions 5 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/manual_pi05_attempt_01

../rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend astra --env-endpoint http://127.0.0.1:8097 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 1 \
 --max-planner-turns 5 --max-actions 5 --planner-timeout-s 300 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/manual_astra_attempt_01

../rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend harness --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 2 \
 --max-planner-turns 5 --max-actions 5 --planner-timeout-s 300 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/manual_harness_attempt_01
```

三条合格短链均为5动作、0.25秒、task_success=false。Astra/Harness内部HTTP请求数未知，planner消息数不替代请求数。模型服务RNG随请求推进；复现还需相同启动和请求顺序，不承诺远端Astra逐bit重复。正式standard/random性能评测未开始。

## 结果分享

[阶段状态](../../../TASK_STATUS.md)、[数据验收](data/README.md)、[几何](geometry/README.md)、[参考视频关系及当前相机](reference/README.md)、[阅读包规则](../../agent_handoff/README.md)。最终DOCX与新的小阅读包待最后实跑归档后生成，不提前声明交付完成。
