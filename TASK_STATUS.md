# LabSim Env_v1 阶段状态

更新于2026-10-21。分支 `codex/lab-cuvette-env-v1`。V0至demo04的源资产、配置、原评分及输出保留。**完整原座装载尚未完成**，以下诊断与接口成绩不替代装载成功或性能评测。

## 当前实际结果

- 场景实际加载单仪器、开盖腔内原A/B座、完整白色6×6架、目标器皿与蓝色邻近器皿。器皿12.5×12.5×67.5 mm为用户名义尺寸，20 g质量仍是假设。Franka是代理，布局为视频关系估计，未真实标定。
- 刚性原座仍有几何阻塞：实际源/派生USD、实例代理及完整变换已审计，两座在必要入口截面上的四个直立方位整个XY可行域均为空，区间证书进一步排除所有直立yaw。12.6 mm只是部分中央参考截面，27 mm仍是射线候选深度。结论不涵盖无依据的斜插或未知弹性机构。启动及每次reset校验资产、装配、路径和控制哈希，改变后重算。
- task/controller/collector已接入现有factories和main统一入口，真实reset/step及主线程RPC已运行；九维执行命令、旧八维映射、effort、原始动作、后继状态及时间均记录。教师明确使用真值，视觉策略默认无器皿真值。
- 原minimal_pick本轮真实回归SUCCESS：518步、8.6333仿真秒、抬升111.84 mm并保持1秒，正常ACT/DP读取通过；不计新装载任务成功。
- preview03实际保存2秒记录后因相机清理崩溃，原错误保留；preview04正常exit0。preview06修复真实projection。旧extract01动态腕相机残差0.966282 mm为历史一个render年龄证据；新fixed01官方zero_delay已实际运行，935/935观测的renderer对当前USD误差小于1e−8 m，最大6.67e−16 m。已测软件渲染状态关联通过，不称为真实物理精度或光学校准，手/前臂部分遮挡仍有定性局限。
- grasp_hold_01/02在接近时失败，03接触锁存失败，全部保留。grasp_hold_04实际通过静止子任务：17.5333秒、双指3秒保持，手内原点最大漂移约1.507 µm、转角0.00294°，exit0。**杯仍由来源架承重，不是悬持或已完成提取。** 没有提高8 N力限、摩擦或驱动增益。
- extract_transport_01在15.7667秒因GRASP_SLIP停止，只抬升约3.504 mm，未清槽。与静止grasp04在15.2667秒前杯pose和命令逐行相同。静置架支撑约+0.501 N、指摩擦Z约−0.305 N，合计平衡0.196 N假设重量。微抬后杯/手相对姿态变化；时序对齐不等于因果确证。
- fixed_orientation01仍GRASP_SLIP，15.6秒停止、未清槽，故主动姿态反馈不是唯一成因。其EXTRACT前3665样本的pose/q/TCP/速度/命令逐值同基线，指接触仅有观测到的浮点聚合差；物理配置不变。
- continuous_latch01实际42.3秒、2537控制步、exit0，保留首次闭合目标以消除latch再张开跳变，8 N上限/摩擦/增益不变。独立sourceclear/grasp/transport均true，最大相对漂移30.42 µm/0.0355°，已实际悬持提取搬运；末端3秒世界漂移230.445 µm超过原200 µm门槛，因此task_success=false，原评分保留。
- 最新preinsert_continuous_latch01实际82.65秒、4958控制步/19836物理步、exit0，独立preinsert_diagnostic成功。清槽/抓持/搬运均true；75.2125秒观察到安全接近，约1 mm处停止后上抬，80.6125秒观察到真实上抬超过8 mm，末1秒漂移0.4835 µm且hold=true。full/native_pair均null，未插入、未开爪、未实际撤离，post_retreat仍unavailable/null。评分不因成功诊断升级为完整装载。
- 新实际记录的ACT/DP读取、RGB/动作/后继与时间检查通过；preview04原格式便携导出约53.96 MB，H5原字节SHA相同，无外部链接/VDS/外置存储。不修改动作、fps或标签；小阅读包默认不含大H5。
- 真实RPC环境API的23项检查全部通过：6个新reset episode、同seed standard/random与B1装配复现、2秒等待不步进、0.05秒动作等于3控制周期、chunk、迟到动作拒绝及原座门控0控制步。random仅检查初始化，不是random任务批次；此次验证器没有调用模型。保留RPC launcher已实际exit0；模型服务RPC关闭后PID消失，非父进程退出码仍未知。
- main真实动作回放已执行Astra03短诊断的15个控制周期，typed关节/夹指命令逐行相同、最大差0 rad/0 m，exit0；实际机器人关节状态在此短窗口也相同。新独立判分仍false，不继承源结果；不宣称完整装载、全状态逐位确定性或接触精度。证据：[实际短回放](docs/lab_cuvette_loading/Env_v1/data/replay_astra03_01_actual_summary.json)。

证据：[几何](docs/lab_cuvette_loading/Env_v1/geometry/README.md)、[相机逐帧残差](docs/lab_cuvette_loading/Env_v1/data/extract01_renderer_USD_dynamic_audit.json)、[提取对齐JSON](docs/lab_cuvette_loading/Env_v1/data/extract01_control_analysis.json)、[力与姿态图](docs/lab_cuvette_loading/Env_v1/data/extract01_control_alignment.png)、[数据验收](docs/lab_cuvette_loading/Env_v1/data/README.md)。

API实证：[live_environment_api_validation.json](docs/lab_cuvette_loading/Env_v1/policy_evidence/live_environment_api_validation.json)。该检查起于仍返回完整debug元数据的旧原始getter；模型tool已独立净化，新getter已完成CPU及真实保存metadata输入契约检查，尚未重启raw RPC实测，不能把23项契约通过当作旧getter观测边界通过。

## 三条真实策略链路已接通

三条链共用真实Isaac RPC、场景、采集器和独立判分，均完成真实双视角图像、模型请求、5个有界动作和后继观测。每条策略动作仅**0.25秒**，加reset渲染fence后记录至0.266667秒；均为standard的preinsert_diagnostic、POLICY_BUDGET、task_success=false。

- π0.5真实checkpoint推理1次，实际5动作。
- GPT-6 Astra direct合格样例为attempt03，实际5个低层动作，没有VLA/完整专家入口。attempt01工具发现失败、0动作；attempt02虽有5动作，但工具返回暴露renderer/debug/depth统计，不作为RGB观测边界合格证据。旧尝试保留。
- RLinf/RPent Harness用真实Astra规划及5次真实π0.5 primitive，实际5动作，不包装专家脚本。

RPC日志证明外部等待及只读观测不推进物理。它们证明接口接通，**不是120秒完整任务性能评测、任务成功率或有效完整失败配额**。证据：[实际三链](docs/lab_cuvette_loading/Env_v1/policy_evidence/real_three_chain_01.json)、[模型与全部尝试](docs/lab_cuvette_loading/Env_v1/policy_backends.md)。

## 未完成与门控

实际提取搬运和最新安全预插入诊断已通过；旧continuous01整体保持false保留。原座插入、承托交接、实际松爪、撤离及释放后3秒稳定仍未完成。完整任务固定5次、random10次、20成功+20有效失败、后续100+100及各策略5+5/20+20正式评测均未开始。没有本轮完整装载成功率。

几何预检、初始化无效、服务异常、进程中断和物理无效单列，不混入物理失败。无实际撤离时post_retreat_window为unavailable，稳定结果为null；末态另存terminal_window。real_calibrated保持false。

## 本轮归档与后续条件

最新安全诊断、4958步读取/相机关联、2546460010字节便携导出及15周期真实动作回放均已完成，本轮报告已生成并完成8页逐页渲染核查，24条运行及5次策略尝试已列入CSV；小阅读包在最终提交推送核验后按该SHA生成。成功源于保持阶段冻结目标并等待实际quiet，判分阈值未放宽；不越过原几何门控。公共getter新边界为CPU和实际保存metadata输入的契约检查，尚未重启raw RPC实测；Astra03/Harness的实际模型tool已独立净化。新[诊断摘要](docs/lab_cuvette_loading/Env_v1/data/preinsert_continuous_latch01_result_summary.json)及[当前资产清单](docs/lab_cuvette_loading/Env_v1/current_asset_scene_manifest.json)保留范围、原始哈希和尺寸依据。

完整原座装载集中缺三项：入口内伸件刚性/可动/弹性结构及依据；器皿底角、入口截面与实际进入方向；正常承托点和装载深度。不凭外观认定弹片，不删除凸起、缩小器皿/碰撞或放宽穿透门槛。

## 复现与分享

main统一入口已实跑，预览、受门控standard/random、读取过滤、视频回看、原格式导出、RPC及三后端准确CLI见[正式入口](docs/lab_cuvette_loading/Env_v1/README.md)。示例必须使用新输出目录；命令存在不代表新批次已执行。已验证改动由根任务阶段提交推送；[最终DOCX](docs/lab_cuvette_loading/Env_v1/results_20261021/LabSim_Env_v1_本轮进展报告.docx)、[Markdown与三段视频](docs/lab_cuvette_loading/Env_v1/results_20261021/LabSim_Env_v1_本轮进展报告.md)及[实际运行表](docs/lab_cuvette_loading/Env_v1/results_20261021/actual_runs.csv)已归档；最终交付SHA由推送后生成的包根清单给出，报告中408932d是运行代码提交。
