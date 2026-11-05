# standard 与固定 Random-10 场景协议

套件版本：`lab_cuvette_loading.scene_suite.v1`。环境版本：`Project_release_v1`；任务仍为完整 `lab_cuvette_loading`，独立评分沿用 `Project_v1_1.independent.v1`，Progress v1.2 负责过程诊断。

验收状态：固定协议、CPU 接口与离线 USD 装配已核验。本次代码的 standard 完整回归、三次物理 reset 和 Random-10 Teacher 执行仍待空闲 GPU；Random-10 当前按候选评测场景使用。历史 standard 成功记录不作为本套件的新运行成绩。

[套件注册表](../../../config/lab_cuvette_loading/Scene_suite_v1/suite.json)固定 `standard` 和 `random_001`–`random_010` 十一个实例。共享加载器应用独立 JSON 覆盖层，使用同一环境和控制实现。没有十一套环境代码；运行中不重新采样，不改变来源槽 A1 或原内部 A 座 `candidate_far_hinge`。

## 用途与身份

| 场景 | 允许用途 | 默认行为 |
|---|---|---|
| standard | 示范、训练数据准备、策略评测 | 省略场景参数；demo/collect 固定使用 |
| random_001–random_010 | policy_evaluation | eval/serve 显式选择；拒绝示范及训练导出 |

[原 standard YAML](../../../config/lab_cuvette_loading/Project_release_v1/standard.yaml)原字节保留。机器人本体、安装和初始关节、10×10×67.5 mm 尺寸假设器皿、20 g 工程质量、原座、摩擦、240/60 Hz 物理/控制、动作接口、双相机安装与标定、评分门槛保持原基线。侧相机全程开启。

`env.mode=standard` 是兼容原 reset 路径的内部值，禁止旧的 reset 随机采样器启动。真正场景身份由 `scene_id`、`scene_suite_version`、`scene_definition_sha256` 和场景指纹共同定义；不能仅凭内部 mode 判断训练用途。H5 属性、嵌入 episode 元数据和配置身份交叉核对，冲突报错。

## 十个固定实例怎样生成

一次性按平移、旋转、光照和组合四类分层生成。PCG64 实际种子 31001–31010 产生幅度/符号，原始 draw、取整规则与结果保存到每个 JSON；reset 只加载已经注册的固定参数。来源架/仪器单项平移绝对值不超过 6 mm，单项 yaw 不超过 1°，DomeLight 强度变化不超过 ±10%；组合项限制在 4 mm / 0.5°。当前列表由参考工作空间和几何关系设计，没有 GPT、π0.5 或待测策略表现参与选择。

表内平移单位为 mm、yaw 单位为度，均相对 standard；光照为原 DomeLight 强度 1000 的倍率。生成种子不是 episode 的控制 RNG 种子。

| scene_id | 生成种子 | 来源架 ΔX, ΔY, Δyaw | 仪器 ΔX, ΔY, Δyaw | 光照倍率 |
|---|---|---|---|---|
| `standard` | 0 | 0.000, 0.000, 0.0000 | 0.000, 0.000, 0.0000 | 1.0000 |
| `random_001` | 31001 | -3.224, 0.000, 0.0000 | 0.000, 0.000, 0.0000 | 1.0000 |
| `random_002` | 31002 | 0.000, -3.987, 0.0000 | 0.000, 0.000, 0.0000 | 1.0000 |
| `random_003` | 31003 | 0.000, 0.000, 0.0000 | -5.913, 0.000, 0.0000 | 1.0000 |
| `random_004` | 31004 | 0.000, 0.000, 0.0000 | 0.000, -5.571, 0.0000 | 1.0000 |
| `random_005` | 31005 | 0.000, 0.000, 0.9102 | 0.000, 0.000, 0.0000 | 1.0000 |
| `random_006` | 31006 | 0.000, 0.000, 0.0000 | 0.000, 0.000, -0.5134 | 1.0000 |
| `random_007` | 31007 | 0.000, 0.000, 0.0000 | 0.000, 0.000, 0.0000 | 0.9200 |
| `random_008` | 31008 | 0.000, 0.000, 0.0000 | 0.000, 0.000, 0.0000 | 1.0722 |
| `random_009` | 31009 | 0.392, -0.442, -0.1483 | -3.914, -2.108, 0.0395 | 0.9889 |
| `random_010` | 31010 | 0.821, 0.554, -0.1823 | -1.060, 0.573, -0.2111 | 1.0033 |

来源架及其槽、底壁、邻杯随来源架整体变换；仪器、盖板、原座及碰撞整体变换。目标座安装关系及局部加载偏移不变，世界抓取点、预插入、搬运终点、目标姿态与撤离方向从相应坐标系计算。Teacher 可以使用已有私有真值适配场景；外部策略继续只接收原公开图像、机器人状态和声明的接触通道。

## 调用与重复次数

准备环境和固定 HF 资产按[ONBOARDING](../../development/ONBOARDING.md)。下列命令均使用新输出目录。

```bash
# 原入口兼容：完整 standard Teacher。
./labsim demo --project-version Project_release_v1 --backend teacher --headless \
  --record-mode collect --record-purpose demonstration \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/standard_demo_001

# 一个固定场景，两次独立 reset/任务，复用同一布局定义。
./labsim eval --project-version Project_release_v1 --scene random_003 \
  --episodes 2 --backend teacher --headless --progress \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/random003_eval_001

# 十个固定场景，每个一次：总共十集，单 GPU 顺序运行。
./labsim eval --project-version Project_release_v1 --suite random10 \
  --episodes-per-scene 1 --backend teacher --headless --progress \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/random10_eval_001

# random 环境服务只用于评测，场景在启动时固定。
./labsim serve --project-version Project_release_v1 --scene random_003 \
  --record-mode eval --record-purpose policy_evaluation --headless --port 8097 \
  --output outputs/lab_cuvette_loading/Scene_suite_v1/random003_rpc_001
```

`--scene` 与 `--suite` 互斥；套件使用 `--episodes-per-scene`，单场景使用 `--episodes`，不混用。`--suite random10 --episodes-per-scene 2` 是十个场景共二十集。`scene_id`、`scene_repetition_index` 和 `suite_episode_index` 分别记录，附 `suite_run_id`。

所有命令可先加 `--dry-run` 查看计划，不启动 Isaac。Random-10 每个成员使用独立子进程，前一进程退出后再启动下一个；不停止其他用户进程。GPU 被占用时保存待运行清单，先完成 CPU 工作。

## 场景验收

eval 可加 `--reset-checks 3`：在正式任务前，于独立 `reset_validation/` 子目录做三次重建，每次原物理控制下自然静置四秒，完整记录初始重力过程。配置与 USD 装配检查使用 1 µm / 0.00001° 数值一致性门槛；稳定后跨 reset 位姿比较使用 0.2 mm / 1°。这些是配置和重复性检查规格，不是实物标定精度。

reset 检查记录配置初态、实际初态、稳定状态、原生/差分速度、源几何穿透、支撑、装配及双相机图。诊断记录按原中断语义闭合，`task_attempt=false`，不计正式 Teacher 完整任务的分母，也不伪造成合格失败。

正式 Teacher 完整执行覆盖抓取、离架、搬运、插入、支撑转移、松爪、脱指、撤离及至少三秒稳定。独立 scorer 决定完整成功；Progress v1.2 只分析阶段。套件检查结果、独立评分、H5 闭合、应用退出和真实 reader batch；初始化失败、环境异常、参考控制器失败和完整成功分列。

每次运行写 `source_identity.json`、解析配置、`launch_identity.json`、`scene_manifest.json` 及 episode 元数据。新增依赖侧记显式覆盖实际读取的 `V0.yaml`、demo04 构建器及关键间接链；历史指纹与旧结果不回写。源码或发布实现变化会产生新运行指纹，不能借此改写历史身份。

CPU 测试及离线 USD 组合只证明协议、几何装配或接口行为。物理 reset、整手可达、完整装载、记录闭合和读取结果由对应新运行收据证明；不能以静态检查通过替代。

## 评测数据读取与汇总

```bash
# RUN 指向一个已经退出的单成员运行目录。
export LABSIM_RUN=outputs/lab_cuvette_loading/Scene_suite_v1/random003_eval_001/random_003/repetition_000
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose policy_evaluation --data-use evaluation \
  --output "$LABSIM_RUN/evaluation_data.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/evaluation_data.hdf5" \
  --data-use evaluation --sample-filter all_valid --policy both \
  --output "$LABSIM_RUN/read_evaluation.json"
```

默认训练/示范导出拒绝 random；显式评测索引与 reader 可读多个场景。`success / failure / all_valid` 原有资格语义保持，场景用途是独立门控。自然失败、诊断、服务异常不互换标签；旧 standard 数据保留兼容。

套件 `suite_manifest.json` 固定计划与场景定义，`suite_summary.json`/CSV 保存全部已请求成员。standard 独立呈现；random 按场景报告成功数、完成数、异常分类和重复分母，平均值为十个场景成功率的等权均值。未启动或未完成成员保留，不以调度进程 exit 0 代替完整任务成功，不根据策略结果静默换种子。

运行录像、H5、日志、图表和反馈包存 ignored `outputs/`，不提交到 docs。完整运行复现命令和实际执行/发布提交随反馈材料交付。
