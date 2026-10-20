# Env_v1 策略后端接入证据

更新：2026-10-21。本页只陈述已有部署、实际探测及适配状态；环境几何和完整任务成绩由主报告记录。

## 实际找到的部署

RPent 项目为 `/home/wujing/Desktop/vla/rpent`，提交 `0d72dfac1e75417564e220e31ba7e4b5d8e83665`。使用其已有 `.venv/bin/python`，没有安装、升级或迁移 Isaac 环境。RPent 是 RLinf/RPent，不是同名 evaluation harness。

本地已有 `RLinf-Pi05-LIBERO-130-fullshot-SFT`，权重为 7,473,091,464 bytes；SHA256 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`。详细文件、统计和配置见 [deployment_inventory.json](policy_evidence/deployment_inventory.json)。

已安装 `rpent-openpi==0.2.2`、`rpent-rlinf==0.3.0`、`openai-codex==0.147.0`、`torch==2.7.1`。RPent 声明依赖 RLinf/openpi 的 `rpent` 分支。安装元数据仅保存 `file:///tmp/rpent-openpi-lock`，没有精确上游 Git SHA，所以该 SHA **未知**；不称为未经改动的官方 OpenPI。运行所用源码、权重与归一化文件均已独立哈希固定；见 [安装源码哈希](policy_evidence/runtime_source_hashes.json)。

## π0.5 的真实契约

使用已有 `rpent.robots.components.pi05_vla_server` / `Pi05VLAClient`，embodiment=`libero`。本轮薄服务器 `pi05_server.py` 继承该真实加载器，增加 `vla.get_metadata`（权重/统计哈希和动作契约）、实际输入/输出日志和延迟；客户端先验证元数据，防止把其他七维服务误认为此 checkpoint。

- 模型基础配置：π0.5，内部 32 action dimensions、horizon 10。
- RPent 已有覆盖：action chunk 5、5 次去噪、实际环境输出 7 维。
- 输入为真实 side RGB 与真实 wrist RGB；缺少腕部图像时拒绝用另一外部视图冒充。
- 状态为相对机器人基座的 EE xyz、axis-angle、两指坐标。Isaac 的两正值指关节显式转换为 LIBERO 的正/负坐标，不使用旧 8 维 agent_pose。
- `get_model` 从 checkpoint 的 `physical-intelligence/libero/norm_stats.json` 加载 quantile normalization。其 `predict_action_batch` 已经过 `Unnormalize` 和 `LiberoOutputs`；客户端不能再次反归一化。
- 七维输出不是关节绝对位置。前六维是 LIBERO OSC 归一化末端增量；安装的 `osc_pose.json` 对应 ±0.05 m、±0.5 rad，基座坐标。第七维是 +闭/-开的增量夹爪方向。
- 本轮明确采用跨环境工程转换：最终平移逐轴最多 2 mm、旋转逐轴最多 0.02 rad；本轮选择 20 Hz policy action（参考现有 LIBERO wrapper 默认 control_freq=20），对应 3 个 60 Hz 控制周期。checkpoint 原训练采样频率没有从现有元数据完整核实，记为未知，不把该工程设置当作训练频率证明。夹爪方向转为有状态、有界的双指总开口，范围 0–80 mm；不把 sign 当米单位。
- 此转换不等价于 LIBERO 的 OSC 动力学，也不是 LabSim 微调模型。模型原始输出、clipping、转换参数及其哈希与最终动作同时保留。

这些依据分别位于安装环境 `rlinf/envs/libero/libero_env.py:_extract_image_and_state`、`rlinf/models/embodiment/openpi/__init__.py:get_model`、`robosuite/controllers/config/default/parts/osc_pose.json`、`robosuite/models/grippers/panda_gripper.py:PandaGripper.format_action`。

## 早期加载探测（保留历史，不代表策略结果）

1. 实际加载该本地 checkpoint，耗时 **28.2 秒**，日志确认从 checkpoint 加载两次所需 norm stats。
2. 实际启动 RPent HTTP 服务，`healthz` 返回 `status=ok`。
3. 已加载时 GPU 总占用 **8099 MiB**，同卡桌面基线约 540 MiB；这是总显存快照，不是每个 tensor 的严格成本。
4. 尚无本轮有效 side/wrist 观测时没有伪造推理。随后调用真实 `shutdown`，进程 exit 0，GPU 释放给仿真。
5. 新薄服务器也已实际加载，模型初始化 26.8 秒，包含权重哈希总计 31.20 秒。`vla.get_metadata` 返回真实模型类和 SHA；客户端实际验证通过，随后 shutdown exit 0。GPU 总占用 8096 MiB。见 [薄服务器实测](policy_evidence/pi05_audited_actual_load_01.json)。仍没有冒充相机推理。

证据：[pi05_actual_load_01.json](policy_evidence/pi05_actual_load_01.json)。完整启动日志保存在 outputs 的 `Env_v1/policy_backends/pi05_load_01/process.log`。这些早期记录只证明加载和服务可用。下方“首轮三条真实链路”已经另外记录本轮真实模型输入、动作执行及后继观测。

## Astra 的真实访问方式

使用已有 ChatGPT 登录。未读取或输出 token；未创建 API key、付费服务或改写认证文件。

RPent `.venv` 默认捆绑旧 Codex runtime，只列出 GPT-5.6 系列。直接复用本机桌面二进制 `/usr/lib/chatgpt/resources/codex`（0.162.0-alpha.2）后，实际 `model/list` 明确返回 `gpt-6-astra`，支持 text/image，默认 reasoning effort=`medium`。不是猜测标识，也没有用其他模型替代。

见 [默认 SDK 模型发现](policy_evidence/codex_model_access.json) 与 [桌面二进制模型发现](policy_evidence/codex_app_model_access.json)。官方模型资料：[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)。本机模型列出本身只证明可发现。随后使用同一已有登录、明确 `gpt-6-astra` / low，实际远端推理在 12.41 秒返回 `ASTRA_ACCESS_CONFIRMED`，见 [访问实测](policy_evidence/astra_actual_access_02.json)。该早期访问探测没有任务图像或机器人动作，本身不称为策略控制接通；后续实际控制见下方。初次 access01 的 per-process MCP 配置键拼写导致进程未启动，其记录保留；修正后 access02 成功。

现有 RPent `CodexPlanner` 支持 `CODEX_BIN`，所以只按进程指定上述已有二进制。采用同一 Toolkit/RPC。direct 模式只开放 `observe`、`bounded_action`、`finish`；没有 VLA 或完整专家脚本入口。每个 bounded_action 只下发一个受限末端或关节动作，IK/插值由同一环境实现。通过本进程配置关闭无关插件、外部 MCP、shell、浏览器、agent、项目说明注入，不修改用户配置文件。桌面 runtime 的 `code_mode_host` 保留启用，作为这三个/四个允许工具的调度入口；关闭它会让工具已经在 MCP 注册、但无法向模型暴露。它不启用 shell 或其他 MCP。评测中 memory 为每 episode 单独创建的空只读目录。

## 本轮新增代码

- `policy_backends/lab_cuvette_env_v1/policy_adapters.py`：公共观测白名单、实际 Pi05VLAClient、明确的 LIBERO 到 LabSim 动作转换。
- `policy_backends/lab_cuvette_env_v1/rpent_extension.py`：继承实际 BaseEnvClient/BaseEnvFacade；RobotSpec、Toolkit、真实短 VLA primitive。没有专家装载 primitive。
- `policy_backends/lab_cuvette_env_v1/policy_runner.py`：三后端同一 RPC 的入口和实际尝试日志；模型等待期间不调用物理 step。
- `policy_backends/lab_cuvette_env_v1/rpent_cli.py`：只扩展当前进程的 `robots` namespace，使已有 RPent registry 正常发现 `labsim_cuvette`，并保留 libero、robocasa、robotwin 等已有后端；不修改已部署 RPent。实际注册检查见 [rpent_registry_check.json](policy_evidence/rpent_registry_check.json)。

薄策略包独立于 `controllers`：已有 `controllers/__init__.py` 会立即导入 Isaac，在模型独立 Python 环境中导入失败；因此策略服务使用上述不依赖 Isaac 的包。包括递归 sensor metadata 边界在内，当前 14 项 CPU 语义/Toolkit/真实 RPent wire 回归已通过；这些测试本身不称为物理或推理端到端证据。
- `config/lab_cuvette_loading/Env_v1/policies/`：π0.5、Astra 的独立配置。

RPent RPC 使用 `POST /call`，请求 `{method,args,kwargs,session_id}`，ndarray 为 `__ndarray__` base64/dtype/shape。环境 reset 返回 `(obs, info)`，step 与 chunk_step 返回 Gym 五元组。Facade 只包装同一环境，不复制场景。Isaac 服务需要在主线程执行所有物理和渲染方法。

## 可调用命令与执行资格

以下为适配器可复现 CLI。实际首轮命令、启动时 Git SHA、各源码 SHA 和 GPU 快照另保存于相应 `*_driver/launch.json`。同名输出已存在时命令会拒绝覆盖，应使用新目录。环境须先由统一入口启动 RPC8097；模型服务只有 π0.5/Harness 需要。

```bash
cd /home/wujing/Desktop/vla/LabSim
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 /home/wujing/Desktop/vla/rpent/.venv/bin/python \
 -m policy_backends.lab_cuvette_env_v1.pi05_server \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/pi05_service_reproduce_01 \
 --model-path /home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT \
 --host 127.0.0.1 --port 8098

# 环境和模型服务已运行后，在另一终端顺序调用；以下是接通检查预算。
/home/wujing/Desktop/vla/rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend pi05 --policy-config config/lab_cuvette_loading/Env_v1/policies/pi05_libero.yaml \
 --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 0 \
 --max-model-requests 1 --max-actions 5 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/pi05_attempt_reproduce_01

/home/wujing/Desktop/vla/rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend astra --policy-config config/lab_cuvette_loading/Env_v1/policies/astra_direct.yaml \
 --env-endpoint http://127.0.0.1:8097 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 1 \
 --max-planner-turns 5 --max-actions 5 --planner-timeout-s 300 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/astra_attempt_reproduce_01

/home/wujing/Desktop/vla/rpent/.venv/bin/python -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend harness --policy-config config/lab_cuvette_loading/Env_v1/policies/harness_pi05.yaml \
 --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
 --subtask preinsert_diagnostic --layout-mode standard --seed 2 \
 --max-planner-turns 5 --max-actions 5 --planner-timeout-s 300 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/harness_attempt_reproduce_01
```

示例 base 坐标只适用于使用这一基座配置的环境；新布局必须使用服务器元数据或显式参数的真实变换。输出目录必须新建，不覆盖旧尝试。

policy_runner 在预算、模型主动结束或服务异常后调用 `env.finalize_episode`，由环境实际判分并 flush 数据；不传入成功布尔值，不终止共享服务器。每次动作均携带 episode ID、观测步号与持续时间。直接策略、Harness 和 π0.5 记录的是同一低层环境协议。

Astra/Codex 内部 HTTP 推理请求数量不可从 SDK 准确读取，因此不会把 RPent agent message 数量当作请求数量；分别记录 planner invocation、message turn、tool call 与实际动作。π0.5 的 `vla.predict` RPC 次数可准确记录。

当前未执行标准/随机 policy 批次，不能报告成功率。完整任务几何被门控阻塞属于几何预检阻塞，不计入物理失败，更不能冒充模型运行失败。

## 主线程环境服务

`demos/lab_cuvette_env_v1/rpc.py` 中 `serve_environment(env, host, port, ready_path=...)` 实际继承已部署 `BaseEnvFacade`。Isaac 专用 Python 只加入 RPent 源码根路径即可导入，未加入模型环境的 site-packages，未安装依赖或替换 numpy。

服务使用单线程 `HTTPServer.handle_request`，所有 reset、step、渲染、判分及 close 均由主线程分发。等待请求期间不调用 `app.update`、`world.step` 或 render，模型推理期间不推进仿真时间。ready JSON 固定配置哈希、基座、动作、物理/控制频率和相机契约；实际移动腕部相机的外参从 `env.get_camera_meta` 按当前状态读取。相邻 `.rpc.jsonl` 保存每次请求前后的仿真步数、时间和线程号。

接口固定白名单包含 env.reset/step/chunk_step/get_observation/render_camera/get_camera_meta/get_task_language/get_env_meta/finalize_episode/close。没有 debug 或教师入口。`healthz` 与 `shutdown` 是本地服务生命周期方法，未注册为模型工具。chunk 请求 `return_all_frames=true` 时，薄 RPC 层将核心环境的 info.all_frames 转成 RPent 所需的首字段 obs_list，保持 Gym 五元组。

真实 RPent HTTP client、主线程 fixture server 的传输回归通过，连同策略及元数据边界共 14 项测试；见 [rpc_transport_validation_02.json](policy_evidence/rpc_transport_validation_02.json)。该 fixture 明确只验证传输和线程，**不是物理仿真或模型控制集成的替代证据**。实际 Isaac 主线程服务和三条策略动作现已执行；下方另列独立真实证据。

## 首轮真实链路测试范围

`--layout-mode standard|random` 显式传入 reset options.mode。`loading` 若在 reset 被几何预检终止，runner 记录 startup_terminated、0 模型请求、0 动作并退出 3；不访问模型或读取额外相机，不计物理插入失败。实际 runner CLI 的这一分支已通过传输 fixture 回归，未称为真实物理实验。

首轮模型接通测试使用 `--subtask preinsert_diagnostic`，π0.5 采用 `--max-model-requests 1 --max-actions 5`。Astra/Harness 的观测与工具调用由真实模型决定，要求读取真实后继观测；不会要求模型宣称成功。实际动作预算用完后由环境独立 finalize POLICY_BUDGET，不继续无限下发。任务能力评测与接通检查分别标记。

## 2026-10-21 同卡常驻模型服务

`pi05_service_01` 已按授权实际加载并等待环境 RPC：加载及权重哈希 32.795 秒，进程启动到 healthz/metadata 就绪 33.721 秒。nvidia-smi 加载前总显存 4168 MiB，加载后 11726 MiB；其中唯一 Isaac 进程 3614 MiB、π0.5 模型进程 7554 MiB。同期 Isaac 正运行，因此这是实际共存快照，不是隔离性能基准或严格峰值。

该加载探测当时输入 NPZ 数量为 0、尚无 inference 日志；随后同一服务实际收到 6 次 checkpoint 请求（π0.5 独立1次，Harness5次），每次输入/原始输出均已保存，原加载探测未覆盖。见 [pi05_service_01_load.json](policy_evidence/pi05_service_01_load.json)。完整实际命令、PID/独立进程组、加载前后快照在 `outputs/lab_cuvette_loading/Env_v1/policy_backends/pi05_service_01/launch.json` 和 `ready_probe.json`；正常停止方式为向该模型 endpoint 调用 `shutdown`，不操作 Isaac 进程。


## 首轮三条真实链路（2026-10-21）

真实运行统一使用 `rpc_01` 的同一 Isaac 场景/采集器/独立判分，`preinsert_diagnostic`、standard 布局；seed 分别为0、1、2。每条预算5个策略动作，每动作0.05秒（3个60Hz控制步/12个240Hz物理步）。每条共15控制步，仿真从相机初始化 fence 后0.016667秒到0.266667秒。实际动作执行时长每条仅 **0.25秒**（另有reset相机fence约0.016667秒），**不是120秒完整任务性能评测，也不代表完整任务能力或成功率**；当前原座完整 loading 仍由几何门控阻塞。三条轨迹均 `task_success=false`、`TASK_INCOMPLETE/POLICY_BUDGET`，不算完整装载失败配额。

- **π0.5**：`pi05_attempt_01`，RPC `episode_0000`，UUID `98a606d1-f0ab-4a4e-89f2-d672b655a9b7`。真实 checkpoint 请求1次、原始输出5×7，5个实际动作及5个动作后继；客户端推理0.603秒、runner墙钟4.962秒。
- **GPT-6 Astra direct**：净化后的 `astra_attempt_03`，RPC `episode_0003`，UUID `14c647b5-7790-4ce0-8c9b-a24b5016ffdf`。实际 `gpt-6-astra` 读取两张真实图像和本体状态，调用 observe和5个bounded_action，总6次工具调用；没有VLA入口。runner墙钟52.303秒，planner响应消息4条。该消息数不代表底层推理HTTP请求数。
- **RLinf/RPent Harness VLA**：`harness_attempt_01`，RPC `episode_0004`，UUID `6469ba9b-c8f7-4c7e-802a-814b1a3b6e77`。实际Astra读取真实图像、生成短语言指令，调用真实π0.5 primitive 5次，每次只执行1个模型动作，并查看实际后继图像；另有observe和finish，共7次工具调用。没有调用教师或将整条专家流程封装成primitive。runner墙钟56.075秒；5次VLA原始5×7输出均保存。

RPC逐请求日志证明同一episode的只读观测不推进物理；本轮运行窗口内，最长外部等待分别0.607、13.910和13.088秒，两端物理步号和仿真时间完全相同。该等待包含模型、planner和传输时间，不将其称为隔离推理延迟。实际动作才推进仿真。相机仍保留主环境声明的运动中renderer/USD小于1 mm差异告警，不宣称完美同步或真实标定。

汇总及所有关联结果/H5/录像SHA：[real_three_chain_01.json](policy_evidence/real_three_chain_01.json)。三条轨迹的实际H5/双视角解码、动作后继时间和普通ACT/DP读取已另由数据检查器独立核验：[只读数据检查](policy_evidence/real_policy_episode_inspection/)。H5没有外部链接；每条15帧两视角CPU解码通过、0黑帧、无未初始化sensor token，保留task_success=false标签，不伪造成功数据。

完整原始记录在 `outputs/lab_cuvette_loading/Env_v1/`：策略端 `policy_backends/{pi05_attempt_01,astra_attempt_03,harness_attempt_01}`；物理数据端 `rpc_01/episode_{0000,0003,0004}`。每个模型启动/执行目录保留精确命令、代码文件哈希和墙钟。模型服务的 `pi05_service_01/service/input_*.npz`、`output_*.npy` 与 `inference.jsonl` 保存真实输入/原始输出。模型服务torch RNG在启动时seed0，之后随请求序列推进；环境seed不等于每次重置模型RNG。复现随机模型原始输出需要相同服务启动状态及请求顺序；不承诺远端Astra输出逐bit重复。

保留的修复前尝试：

- `astra_attempt_01`/RPC episode0001：真实模型可访问，但禁用code_mode_host使MCP工具未暴露，0动作，记录明确no_transitions，不纳入有效物理失败。
- `astra_attempt_02`/RPC episode0002：真实5动作，但camera_meta包含renderer_debug和depth诊断字段。原始物理记录保留，**不作为默认RGB观测边界验收证据**；最终Astra用attempt03重跑。

最终Toolkit仅输出显式sensor_meta白名单（K、安装、外参、分辨率、色彩和采样时间等）；renderer_debug、depth annotator、完整引擎设置及配置诊断不进入模型。完整metadata只写本地 `camera_meta_audit.jsonl`，公开快照另存 `policy_camera_meta.json`。实际Astra03/Harness保存的tool state中均核查没有 `renderer_debug` 或 `distance_to_image_plane`。上面两个历史尝试的原始评分和录像未改写，排除原因只记在新汇总中。


## 真实环境API与资源生命周期验收

在保留的同一8097实际Isaac服务上，`scripts/validate_lab_cuvette_env_v1_live.py` 已运行完成，23项检查全部通过，进程exit0；证据见 [live_environment_api_validation.json](policy_evidence/live_environment_api_validation.json)。新增API专用episode0005–0010全部保留，不混入正式standard/random任务批次。

实际覆盖公共观测、任务语言、双相机render/meta、2.014秒墙钟等待时关节/步号/仿真时间不变、零关节速度0.05秒恰好3控制步、两动作chunk/allframes、非法duration和迟到step拒绝且无步进、finalize/终止后拒绝、旧episode拒绝、连续reset及实际q/TCP/槽位ID复现。standard seed41及random seed7各比较一次重复复位，观察到q、TCP及quaternion差均为0；这是本次重复初态证据，不是广泛确定性保证。

random seed7实际选择B1；架体平移[0.250191,0.794428]mm，仪器整机平移[0.551371,-0.549586]mm。两次保存的装配配置一致，目标仍使用instrument-relative内部座，器皿源槽初态containment=true、已记录rack穿透0。该检查只验合法随机初始化及装配关系，未执行抓取、可达性或完整random任务。相关本地initial_debug是审计旁证，未通过公共观测交给模型。

完整loading reset真实返回`GEOMETRY_PRECHECK_BLOCKED`、terminated=true、0控制/插入步；仅保留reset重力/相机初始化4个物理步。其后动作被拒，物理时间不变。π服务predict日志在门控前后均6条，无新模型推理，未把预检阻塞计为物理插入失败。

复现须先按[统一环境入口](README.md)启动一个新的8097服务，并换新输出目录；本命令最后会正常关闭该环境：

```bash
/home/wujing/Desktop/vla/rpent/.venv/bin/python -u scripts/validate_lab_cuvette_env_v1_live.py \
 --endpoint http://127.0.0.1:8097 \
 --server-output outputs/lab_cuvette_loading/Env_v1/manual_rpc_01 \
 --output outputs/lab_cuvette_loading/Env_v1/live_api_reproduce_01 \
 --evidence outputs/lab_cuvette_loading/Env_v1/live_api_reproduce_01_summary.json \
 --pause-s 2 --shutdown
```

实际环境已收到shutdown并关闭8097；主进程已从保留会话62219实际轮询确认Isaac launcher exit0。π模型也已单独RPC shutdown，PID609634消失、8098拒绝连接，GPU总占用从8408降至533MiB；不是向共享Isaac进程发送kill。模型退出码未由本验证器waitpid取得，明确为unknown。证据：[pi05_service_01_shutdown.json](policy_evidence/pi05_service_01_shutdown.json)。

本次保留服务是在后续默认metadata净化修补前启动的，所以其get_camera_meta仍含renderer debug；实际模型Toolkit已经独立白名单过滤并通过Astra03/Harness记录检查。API验收记录了该事实，没有把旧常驻实例称为新代码重载后的净化验证。后续源代码default getter修复已有CPU验证；最终Astra03/Harness实际净化tool边界合格。该旧常驻RPC不作为新getter重载实测证据。

阅读包可只携带 [live_environment_api_validation_summary.json](policy_evidence/live_environment_api_validation_summary.json)（小于15KB）；完整23项检查和原始请求trace留在工程中，不把大量重复cfg/q放入阅读包。
