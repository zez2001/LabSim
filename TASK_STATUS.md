# lab_cuvette_loading Env_v1 阶段状态

更新于 **2026-10-21 00:33（Asia/Shanghai）**。开发分支：`codex/lab-cuvette-env-v1`。本阶段起点提交：`e7e00996ed0b5c0f24e36d10ad5cbeefe58c4462`；本页描述其后的开发工作，提交及远端状态以实际 Git 记录为准。

**最终目标尚未完成。** 本轮已完成离线几何审计、历史数据复核和部分真实模型资源访问；此时间点尚无 Env_v1 新场景的实际 Isaac 连续运行、完整装载成功或策略控制轨迹。以下状态随实际运行逐阶段更新，不能将接口代码或单元测试当作物理演示。

## 已执行并有证据

- **参考场景核查。** 已直接解码原视频六个关键帧并重新查看四张照片，保存原媒体哈希、参考关系标注和俯视布局提案。提案使用完整 6×6 架、单台仪器、明确的整机 yaw 与侧向偏移；位置为视频关系估计，Franka 为机器人代理。新场景的实际可见性、可达性及全过程碰撞仍待仿真验收。[参考证据](docs/lab_cuvette_loading/Env_v1/reference/README.md)
- **原座几何审计。** 实际读取源及当前派生 USD 的完整变换、12.5×12.5×67.5 mm 器皿和 A/B 原座。0°/90°/180°/270°直立方位的整个必要 XY 可行域均为空；区间证书进一步排除所有直立 yaw 穿过该必要入口截面。入口内伸结构与器皿底部实际材料冲突，不能由中央线的 12.6 mm 宽度推出可插入。结论不覆盖任意倾斜六自由度路线或未知弹性机构。[几何入口及证据](docs/lab_cuvette_loading/Env_v1/geometry/README.md)
- **几何缓存失效检查。** 00:32 实际校验当前代码与已完成快照，结果为 `current=false, reason=binding_changed`。这是后续新增环境/教师源码触发的正常失效，不能继续将历史快照当当前门控。新 launcher 会在启动前重算；重算完成前不声称当前输入已通过审计。
- **独立判分逻辑。** 13 项状态序列单元测试实际通过，包括 unknown 保留、真实接触/脱指、合法再次夹持、独立子任务和撤离窗口语义。合成测试不是物理成功。完整 loading、`grasp_hold`、`extract_transport`、`preinsert_diagnostic` 分开判分；诊断通过不进入完整装载成功索引。
- **历史抓持复核。** 只读分析 demo04 第三条实际轨迹 18,461 个物理记录：来源提取与搬运已发生，但搬运阶段有约 3.986 mm 底部原点相对漂移、3.930°相对转角。53 mm 抓取参考点漂移约 0.561 mm，不能把原点位移解释成纯轴向滑移。历史原评分与输出未改写；这不是本轮新仿真。[历史证据](docs/lab_cuvette_loading/Env_v1/scorer/README.md)
- **现有数据读取回归。** 真实历史 demo03 成功 H5 已通过 ACT 和 Diffusion 正常读取；原 minimal_pick 的 518 步 H5 读取回归通过。新 success/failure/all_valid 过滤及采集契约经过测试；旧记录缺少有效性证据时保持 unknown，没有改写为成功或有效失败。这不等于原任务物理运行回归或 Env_v1 新数据验收。[数据证据](docs/lab_cuvette_loading/Env_v1/data/README.md)
- **π0.5 / Harness 真实资源。** 本机 RPent 的实际 π0.5 LIBERO checkpoint 已真实加载，薄服务及元数据访问成功后正常关闭。Harness 已通过真实 RPent 注册、Toolkit 与 HTTP 协议检查；尚未用 Env_v1 任务图像调用 VLA 并执行物理动作。加载与协议检查不代表策略链路接通。
- **Astra 真实访问。** 已使用现有登录及实际 `gpt-6-astra` 完成远端文本推理探测。尚无本轮任务图像、机器人动作或后继观测，不计为 Astra 控制 episode。[三后端访问及版本证据](docs/lab_cuvette_loading/Env_v1/policy_backends.md)

## 代码已建立、尚待实际环境验证

正式 task/controller/factory/collector 与统一 launcher 已建立；环境提供 reset、step、chunk_step、观测、相机、语言及 close 接口。固定 side_camera 与真实 hand 子节点 wrist_camera、同步推理等待、九维执行动作及双指 effort 记录、有界接触锁定教师、分区支撑采集和独立判分已经接入代码。

尚未完成的实跑验收包括：新场景加载/reset/资源清理、连续双视角渲染与黑帧检查、静止夹持 3 秒、实际提取搬运 3 秒保持、预插入诊断、便携新 episode 的实际读取，以及三个后端真实任务观测→模型请求→动作→后继观测闭环。代码存在不代表这些项目已经通过。

完整原座装载目前存在独立几何阻塞；预检阻塞单列，不能算作物理插入失败。固定 5 次、random 10 次、首批 **20 条完整成功 + 20 条有效物理失败**、后续 100+100，以及三后端 5+5/20+20 评测均**未开始**，没有可报告的本轮成功率。

## 当前命令与执行资格

从工程根目录运行，所有输出目录必须是新的路径。以下离线审计入口及判分测试已实际执行；审计参数和源码变化后须重新运行：

```bash
bash demos/lab_cuvette_external/usd_python.sh \
  -m demos.lab_cuvette_env_v1.geometry_audit \
  --config config/lab_cuvette_loading/Env_v1/native.yaml \
  --output docs/lab_cuvette_loading/Env_v1/geometry/cache --ensure \
  --geometry-site /home/wujing/Desktop/vla/physicalrsi-runtime/sim-env/lib/python3.11/site-packages

../labutopia-env/bin/python -m unittest discover -s tests \
  -p test_lab_cuvette_env_v1_scorer.py -v
```

以下为当前源码提供的准确 CLI，**截至本页时间点尚未实测**。GUI 默认开启；加 `--headless` 运行无窗口模式。正式 loading 仍应受当前几何预检阻塞：

```bash
bash demos/lab_cuvette_env_v1/run.sh --mode preview \
  --config config/lab_cuvette_loading/Env_v1/grasp_hold.yaml \
  --output outputs/lab_cuvette_loading/Env_v1/preview_01

bash demos/lab_cuvette_env_v1/run.sh --mode teacher \
  --config config/lab_cuvette_loading/Env_v1/grasp_hold.yaml \
  --output outputs/lab_cuvette_loading/Env_v1/grasp_hold_01

bash demos/lab_cuvette_env_v1/run.sh --mode teacher \
  --config config/lab_cuvette_loading/Env_v1/extract_transport.yaml \
  --output outputs/lab_cuvette_loading/Env_v1/extract_transport_01

bash demos/lab_cuvette_env_v1/run.sh --mode teacher \
  --config config/lab_cuvette_loading/Env_v1/preinsert.yaml \
  --output outputs/lab_cuvette_loading/Env_v1/preinsert_01

bash demos/lab_cuvette_env_v1/run.sh --mode serve --port 8097 \
  --config config/lab_cuvette_loading/Env_v1/preinsert.yaml \
  --output outputs/lab_cuvette_loading/Env_v1/rpc_01
```

真实模型服务加载命令、各后端 CLI 及其当前执行资格见[策略后端文档](docs/lab_cuvette_loading/Env_v1/policy_backends.md)。未进行的端到端评测不因提供命令而视为完成。

## 下一项可执行工作与必要信息

1. 冻结本轮代码，自动刷新几何绑定；顺序运行场景预览和三个抓持/搬运子实验，核查布局、全程双视角、实际接触与姿态漂移。保留全部失败和原始信号。
2. 用真实新场景观测接通三个策略闭环，分别记录至少一次真实模型请求、有效动作和后继观测；模型访问已经可用，环境集成仍需实跑。
3. 原座恢复完整装载需要集中补充：入口内伸件是刚性、可动还是弹性结构及其依据；实际器皿底角/入口截面与进入方向；正常承托位置与装载深度。27 mm 当前只是源座射线得到的几何候选，不能当作实测装载深度。

源 CAD/USD、V0 至 demo04 资产、配置、原数据、原评分及结果继续保留。不得靠删除凸起、缩小碰撞、放宽穿透门槛或假成功标签绕过阻塞。`real_calibrated` 保持 false。本轮结果阅读包在实际运行证据、提交和推送核对完成后另行生成；此页不是完整交付完成声明。
