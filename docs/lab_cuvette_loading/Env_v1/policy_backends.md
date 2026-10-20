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

## 已实际执行

1. 实际加载该本地 checkpoint，耗时 **28.2 秒**，日志确认从 checkpoint 加载两次所需 norm stats。
2. 实际启动 RPent HTTP 服务，`healthz` 返回 `status=ok`。
3. 已加载时 GPU 总占用 **8099 MiB**，同卡桌面基线约 540 MiB；这是总显存快照，不是每个 tensor 的严格成本。
4. 尚无本轮有效 side/wrist 观测时没有伪造推理。随后调用真实 `shutdown`，进程 exit 0，GPU 释放给仿真。
5. 新薄服务器也已实际加载，模型初始化 26.8 秒，包含权重哈希总计 31.20 秒。`vla.get_metadata` 返回真实模型类和 SHA；客户端实际验证通过，随后 shutdown exit 0。GPU 总占用 8096 MiB。见 [薄服务器实测](policy_evidence/pi05_audited_actual_load_01.json)。仍没有冒充相机推理。

证据：[pi05_actual_load_01.json](policy_evidence/pi05_actual_load_01.json)。完整启动日志保存在 outputs 的 `Env_v1/policy_backends/pi05_load_01/process.log`。**checkpoint 实际加载不代表完整策略接通**；真实模型输入、动作执行及后继观测待实际环境接口运行后单独更新。

## Astra 的真实访问方式

使用已有 ChatGPT 登录。未读取或输出 token；未创建 API key、付费服务或改写认证文件。

RPent `.venv` 默认捆绑旧 Codex runtime，只列出 GPT-5.6 系列。直接复用本机桌面二进制 `/usr/lib/chatgpt/resources/codex`（0.162.0-alpha.2）后，实际 `model/list` 明确返回 `gpt-6-astra`，支持 text/image，默认 reasoning effort=`medium`。不是猜测标识，也没有用其他模型替代。

见 [默认 SDK 模型发现](policy_evidence/codex_model_access.json) 与 [桌面二进制模型发现](policy_evidence/codex_app_model_access.json)。官方模型资料：[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)。本机模型列出本身只证明可发现。随后使用同一已有登录、明确 `gpt-6-astra` / low，实际远端推理在 12.41 秒返回 `ASTRA_ACCESS_CONFIRMED`，见 [访问实测](policy_evidence/astra_actual_access_02.json)。该探测没有任务图像或机器人动作，所以仍不能称为策略控制接通。初次 access01 的 per-process MCP 配置键拼写导致进程未启动，其记录保留；修正后 access02 成功。

现有 RPent `CodexPlanner` 支持 `CODEX_BIN`，所以只按进程指定上述已有二进制。采用同一 Toolkit/RPC。direct 模式只开放 `observe`、`bounded_action`、`finish`；没有 VLA 或完整专家脚本入口。每个 bounded_action 只下发一个受限末端或关节动作，IK/插值由同一环境实现。通过本进程配置关闭无关插件、外部 MCP、shell、浏览器、agent、项目说明注入，不修改用户配置文件。评测中 memory 为每 episode 单独创建的空只读目录。

## 本轮新增代码

- `policy_backends/lab_cuvette_env_v1/policy_adapters.py`：公共观测白名单、实际 Pi05VLAClient、明确的 LIBERO 到 LabSim 动作转换。
- `policy_backends/lab_cuvette_env_v1/rpent_extension.py`：继承实际 BaseEnvClient/BaseEnvFacade；RobotSpec、Toolkit、真实短 VLA primitive。没有专家装载 primitive。
- `policy_backends/lab_cuvette_env_v1/policy_runner.py`：三后端同一 RPC 的入口和实际尝试日志；模型等待期间不调用物理 step。
- `policy_backends/lab_cuvette_env_v1/rpent_cli.py`：只扩展当前进程的 `robots` namespace，使已有 RPent registry 正常发现 `labsim_cuvette`，并保留 libero、robocasa、robotwin 等已有后端；不修改已部署 RPent。实际注册检查见 [rpent_registry_check.json](policy_evidence/rpent_registry_check.json)。

薄策略包独立于 `controllers`：已有 `controllers/__init__.py` 会立即导入 Isaac，在模型独立 Python 环境中导入失败；因此策略服务使用上述不依赖 Isaac 的包。10 项 CPU 语义及真实 Toolkit 边界回归已通过，未称为物理或推理端到端测试。
- `config/lab_cuvette_loading/Env_v1/policies/`：π0.5、Astra 的独立配置。

RPent RPC 使用 `POST /call`，请求 `{method,args,kwargs,session_id}`，ndarray 为 `__ndarray__` base64/dtype/shape。环境 reset 返回 `(obs, info)`，step 与 chunk_step 返回 Gym 五元组。Facade 只包装同一环境，不复制场景。Isaac 服务需要在主线程执行所有物理和渲染方法。

## 可调用命令与执行资格

以下为适配器实际 CLI。原 RPent 服务器及带元数据薄服务器加载均已实际执行。下列完整策略命令须在新环境服务就绪后实际执行，不能据命令存在声称通过。

```bash
cd /home/wujing/Desktop/vla/LabSim
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 /home/wujing/Desktop/vla/rpent/.venv/bin/python \
 -m policy_backends.lab_cuvette_env_v1.pi05_server \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/pi05_server_01 \
 --model-path /home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT \
 --host 127.0.0.1 --port 8098

/home/wujing/Desktop/vla/rpent/.venv/bin/python \
 -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend pi05 --policy-config config/lab_cuvette_loading/Env_v1/policies/pi05_libero.yaml \
 --env-endpoint http://127.0.0.1:8097 \
 --vla-endpoint http://127.0.0.1:8098 --robot-base-position-m -0.3 0 0.74 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/pi05_attempt_01

/home/wujing/Desktop/vla/rpent/.venv/bin/python \
 -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend astra --env-endpoint http://127.0.0.1:8097 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/astra_attempt_01

/home/wujing/Desktop/vla/rpent/.venv/bin/python \
 -m policy_backends.lab_cuvette_env_v1.policy_runner \
 --backend harness --env-endpoint http://127.0.0.1:8097 \
 --vla-endpoint http://127.0.0.1:8098 --robot-base-position-m -0.3 0 0.74 \
 --output outputs/lab_cuvette_loading/Env_v1/policy_backends/harness_attempt_01
```

示例 base 坐标只适用于使用这一基座配置的环境；新布局必须使用服务器元数据或显式参数的真实变换。输出目录必须新建，不覆盖旧尝试。

policy_runner 在预算、模型主动结束或服务异常后调用 `env.finalize_episode`，由环境实际判分并 flush 数据；不传入成功布尔值，不终止共享服务器。每次动作均携带 episode ID、观测步号与持续时间。直接策略、Harness 和 π0.5 记录的是同一低层环境协议。

Astra/Codex 内部 HTTP 推理请求数量不可从 SDK 准确读取，因此不会把 RPent agent message 数量当作请求数量；分别记录 planner invocation、message turn、tool call 与实际动作。π0.5 的 `vla.predict` RPC 次数可准确记录。

当前未执行标准/随机 policy 批次，不能报告成功率。完整任务几何被门控阻塞属于几何预检阻塞，不计入物理失败，更不能冒充模型运行失败。

## 主线程环境服务

`demos/lab_cuvette_env_v1/rpc.py` 中 `serve_environment(env, host, port, ready_path=...)` 实际继承已部署 `BaseEnvFacade`。Isaac 专用 Python 只加入 RPent 源码根路径即可导入，未加入模型环境的 site-packages，未安装依赖或替换 numpy。

服务使用单线程 `HTTPServer.handle_request`，所有 reset、step、渲染、判分及 close 均由主线程分发。等待请求期间不调用 `app.update`、`world.step` 或 render，模型推理期间不推进仿真时间。ready JSON 固定配置哈希、基座、动作、物理/控制频率和相机契约；实际移动腕部相机的外参从 `env.get_camera_meta` 按当前状态读取。相邻 `.rpc.jsonl` 保存每次请求前后的仿真步数、时间和线程号。

接口固定白名单包含 env.reset/step/chunk_step/get_observation/render_camera/get_camera_meta/get_task_language/get_env_meta/finalize_episode/close。没有 debug 或教师入口。`healthz` 与 `shutdown` 是本地服务生命周期方法，未注册为模型工具。chunk 请求 `return_all_frames=true` 时，薄 RPC 层将核心环境的 info.all_frames 转成 RPent 所需的首字段 obs_list，保持 Gym 五元组。

真实 RPent HTTP client、主线程 fixture server 的传输回归通过，连同策略边界共 11 项测试；见 [rpc_transport_validation.json](policy_evidence/rpc_transport_validation.json)。该 fixture 明确只验证传输和线程，**不是物理仿真或模型控制集成的替代证据**。实际 Isaac 服务运行及策略动作待主环境就绪后记录。
