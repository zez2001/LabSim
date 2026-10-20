# LabSim Env_v1 阶段状态

更新于 2026-10-21 01:08 Asia/Shanghai。分支 `codex/lab-cuvette-env-v1`；从 `e7e0099` 独立建立，V0 到 demo04 的代码、资产和原输出未覆盖。

**完整装载尚未完成。** 当前原座入口存在实际材料干涉；正在继续不依赖该实物信息的控制、观测、数据及策略接入工作。不能把下面的诊断结果计为原座装载成功。

## 本轮已实际完成

- 原视频六帧及四张照片重新核对；新布局有一台仪器、完整白色6×6架、目标器皿和远角蓝色器皿，Franka 是代理机器人。布局采用视频关系估计，未真实标定。
- 当前12.5×12.5×67.5 mm器皿、A/B原座及完整变换重新离线审计。两座入口必要XY可行域在四个直立正交方位均为空，区间证书进一步排除所有直立yaw。结论不涵盖未经依据的倾斜路径或未知弹性机构。中央12.6 mm参考截面不能证明整条路径可通行。
- 审计绑定实际依赖文件/配置/装配/控制实现哈希；启动和每次reset均检查，相关输入变化后离线重算。原27 mm深度仍仅为源几何中心射线候选，不是实测承托深度。
- 正式任务、教师、独立判分、采集器已注册现有factories，`main.py --config-name lab_cuvette_env_v1` 已实际运行。模型默认观测排除物体真值；教师明确使用真值。
- 新同步环境提供reset/step/chunk_step/观测/相机/语言/close，显式9维执行命令和旧8维单指映射、阶段effort、原始输出与转换均记录。等待模型时不步进。
- `minimal_pick_regression_20261021_01` **实际专家回归SUCCESS**：518控制步、8.6333仿真秒、抬升111.84 mm、双指保持1秒、进程exit0；正常ACT和DP成功读取均通过。
- `preview_03` 2秒/120步，图像/H5已保存，但Camera.destroy导致退出崩溃；保留原错误。`preview_04` 2秒正常exit0， scoped传感器清理修复通过。
- `grasp_hold_01/02` 均在11秒接近阶段因TCP偏差失败。独立URDF FK证实物理TCP读取正确，而重复IK分支和逐关节限速破坏了目标跟踪。新增固定目标缓存、连续IK初值、声明容差及连续关节命令后，`grasp_hold_03` 的固定目标命令不再漂移，命令FK误差从最高104.6 mm降至47.55微米。
- `grasp_hold_03` 仍失败：首次接触冻结到测量宽度会比上一已下发目标更宽，92次接触/失触循环、0次最终锁存。已修为有重量/摩擦/刚度依据的有界正开口，且不宽于上一闭合命令；未提高8 N上限、摩擦或增益。
- `grasp_hold_04` **静止夹持子任务实际通过**：17.5333秒、1051控制步、4208物理步；连续双指3秒保持，手内原点最大漂移1.507微米、转角0.00294度。未提取、未插入、未释放，完整装载资格仍为false/null。实际进程exit0。
- 两相机均为真实不同renderproduct：side固定世界、wrist为hand子节点。grasp04从第一有效非0传感器token开始，双路无黑帧/重复帧，传感器时间减engine origin后与观测差≤0.914微秒；初始化4个物理步之前的step0和早期重力响应全部记录。
- **腕部画面尚未合格**：直接USD、物理hand×固定mount及既有Fabric矩阵一致，实际RGB却未显示预计器皿。不能因挂载和时间正确宣称视野正确；下一步读取渲染CameraParams/深度定位。CPU PhysX仍保留，当前显示变换采用显式USD写回；未迁移动力学后端。
- 新实际episode的ACT/DP `all_valid`读取、首中末图像/动作/后继状态及便携H5检查通过；success/failure/all_valid保持独立资格。诊断成功不进入完整loading BC，几何阻塞/服务异常不计物理失败。原始历史评分未改写。

## 真实模型资源与集成状态

π0.5实际checkpoint已加载并正常退出；已核实本机RLinf/RPent/OpenPI fork版本、checkpoint哈希与LIBERO7维OSC动作语义，未把它误当旧8维关节位置。Astra使用现有登录和实际gpt-6-astra ID完成真实文本请求。Harness使用真实RPent BaseEnvFacade/BaseEnvClient及Toolkit契约；主线程HTTP传输、旧episode保护与CPU测试通过。

**三后端的Env_v1图像→模型→动作→后继观测尚未完成**，待腕图像问题定位后顺序运行。访问探测或fixture协议测试不算策略物理集成。真实图像策略默认无真值，Astra直接模式无VLA/完整专家入口。

## 未完成项目及门控

实际提取/搬运有界保持、预插入、整条原座装载、支撑交接/松爪/撤离均尚未在Env_v1验收。完整任务固定5次、random10次，以及20成功+20物理有效失败、100+100扩量均未开始；三后端5+5/20+20正式评测亦未开始。没有本轮完整装载成功率。

最近已实测入口：

```bash
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py \
 --config-name lab_cuvette_env_v1 --env-mode teacher --subtask grasp_hold \
 --headless --output outputs/lab_cuvette_loading/Env_v1/grasp_hold_04
```

输出目录必须换新，不覆盖旧结果。新数据正常读取、导出命令见 `docs/lab_cuvette_loading/Env_v1/data/README.md`；几何证据见 `geometry/README.md`；模型资源与协议见 `policy_backends.md`。这些文档中尚未实跑的命令不能当作验证结果。

## 下一项工作与必要实物信息

先定位真正渲染的腕部view/projection，继续提取搬运，完成同一RPC下三条真实模型链。随后按实际稳定性决定是否扩量，保留全部失败。

原座完整装载集中缺三项：入口内伸件究竟是刚性/可动/弹性结构及依据；器皿底角/座入口限制截面和实际进入方向；真实承托位置与装载深度。未获得依据前，不删除凸起、缩小器皿或碰撞、不放宽穿透门槛。`real_calibrated=false`。

已验证批次持续提交并推送；新阅读包只含本轮改动与结果，不默认打包原始H5或历史整套输出。
