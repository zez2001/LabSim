# lab_cuvette_loading V0_ext01 外部资产接入结果

本轮实际替换器皿及干扰器皿、仪器外壳和两候选内部座的视觉与碰撞。来源架继续为V0参数化代理，未替换；机器人复用旧Franka。没有隐藏旧代理装载座。当前完成坐标标准化及独立加载，物理精度和配对关口未通过，完整任务与standard/random未放行。calibrated=false。

最关键的问题是：文件器皿约14.85×14.85×67.5mm，两候选部件的部分限制截面约12.6mm；声明的居中直立竖直路径存在实际边界相交。旧15mm来源孔只有约75微米单侧名义余量，实际支撑抖动，烹饪表示误差及源几何桌面越界均超过该尺度。不能归因为单纯控制器问题，也没有为成功缩小源器皿、放大孔或移除墙。

## 分阶段状态

| 项目 | 状态 | 限制 |
| --- | --- | --- |
| 加载成功 | passed | 五个派生USD独立加载；必要引用已解析；不代表物理通过 |
| 几何接入验收 | coordinate_geometry_passed_with_identity_limits | 单位/朝向/defaultPrim/实际顶点尺寸通过；源模型真实尺寸及身份未确认 |
| 配对装载可行性 | blocked_identity_and_geometry | 两候选座给定居中竖直姿态有网格边界相交；其他方向未穷举；身份未知 |
| 物理配置及限定检查 | partially_observed_NOT_accepted_for_precision | 质量惯量读回及落稳/侧壁接触有证据；烹饪偏差约0.312mm，源几何桌面越界约0.28mm；旧架抖动；机器人惯量未校准 |
| 子任务 | grasp_hold_phase_passed_release_failed | 桌面局部诊断；双指抬升保持约8.625s，最后释放倾倒，整条诊断失败 |
| 完整任务 | not_executed_blocked | 没有完整任务执行器放行；新装载判据未冻结；完整成功0 |
| standard和random | blocked_0_full_episodes | 仅运行关口；未开展10次/20次完整批次；随机种子5000至5019已保存 |
| 真实一致性 | not_verified | 未做真实尺寸/材料/机器人/相机校准或real2sim gap评估 |

## 来源与保护

- 分支：codex/lab-cuvette-external-assets；起始提交44b2cf46a2bb16330be076ee5c528dc2c0054623。实际运行commit、dirty和源码SHA均在每次provenance及source_snapshot中。
- 原压缩包SHA256：`62f96e93b3a179d17ed00738a16213785465ae704bd5f3f6f94d17e6f7934fce`，与交接值一致。原包及解压内容只读复制，包内Python脚本仅阅读，未执行。
- V0保护复核：4036个文件、3111个唯一inode，SHA256全部一致，旧inode和硬链接计数均未改变。
- 外部TestTube_629.usd含/root绝对OBJ引用，保留来源记录，未作正式入口；没有原始STEP、尺寸图或真实测量。

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| _bake_testtube.py | 7239 | 744dd4b6f85922c509f217c1a1fe4a2efe51f4d02110f8c61c5a9830e8227def |
| _verify_baked.py | 1465 | 40613c5b0d74c325ddf1322299878a9dcb7628d31a32c0a89c509ac712c8c20f |
| newnew4.usd | 1325056 | 8261714be7250b61466e9b3537a25438a5cc441c20a465ea6b3c27b43383a1dc |
| TestTube_629.usd | 151 | dfb0480b5fa8106fdc444fded0bff2dbaa018409839d70207a6319392073b19f |
| TestTube_Baked.usd | 173738 | c7d6897a1e555c282ac30a53e95cb872fda4e112821d2a013a9612bd40e39f36 |
| 试管/试管.mtl | 237 | 0c16f7b377214be2eaa8ff191b5fbbbbb25662f621cabd00601f477e27526257 |
| 试管/试管.obj | 280772 | bd21a0050e832662bb08995d20fa4a3b179d80c103dbbf0546924dfbc9add0af |

## 资产角色对应

| 任务角色 | V0实现 | 外部文件或prim | 替换状态 | 依据与待确认 |
| --- | --- | --- | --- | --- |
| target_vessel | V0 Cube empty cup | TestTube_Baked.usd /TestTube/Mesh | replaced visual and dynamic compound collision | source USD vertices match packaged OBJ within1.2e-8m；actual vessel model and matching instrument unconfirmed |
| distractor_vessels | V0 cuvette_debug | same external vessel_debug.usda, two copies | replaced in diagnostic scene | explicit source reuse；not proof of real distractor identity |
| source_rack | V0 parameterised 6x8 rack | no rack supplied | NOT replaced; independent V0 proxy copy | package inventory；true slot dimensions and matching vessel |
| instrument_shell | V0 seven Cube proxy | newnew4.usd /RotatedRoot | replaced visual and static triangles | CAD converter metadata and assembly geometry；real model identity and dimensions unverified |
| target_holder | V0 4 walls and shared Base | two candidate instance paths in source_geometry.json | both source parts preserved and collidable; NONE selected as confirmed target | geometry only；which component and loading direction; no hidden V0 holder |
| neighbour_parts | V0 empty neighbour Cube slot | all 8 instrument proxy meshes once | external assembly retained | instance proxy traversal；semantic labels unknown |
| robot_and_gripper | existing Franka USD | assets/robots/Franka.usd | reused | repository asset；real neo model and inherited inertia units |
| table_and_background | V0 synthetic table and background | FixedCuboid/GroundPlane/DomeLight | synthetic proxy retained; table enlarged1.6x1.5m for supplied instrument, no size scaling of CAD | explicit installation assumption；true table, camera and layout measurements; decorative V0 background omitted from diagnostics |

## 坐标与尺寸

- 场景及派生USD为米和Z-up，defaultPrim=/Asset。器皿原Y-up做一次+90度X旋转；仪器原Z-up保留/RotatedRoot已有+90度X旋转，只叠加毫米到米及原点平移，不重复旋转。
- 以实际变换后顶点AABB的XY中心和最低顶点定义资产原点，原点不等同质心。源Mesh局部点先乘原完整USD变换M，再按行向量乘转换矩阵T：p_normalized=[p_source_world,1]@T。T保存在conversion.json，逐实例记录避免prototype重复计数。
- 仪器遍历普通Traverse得到0 Mesh，遍历instance proxies得到8 Mesh，包含两个同prototype候选座；本版静态碰撞每个实际实例只计一次。源材质绑定和GeomSubset均记录，外壳视觉保留源材质，器皿透明是本轮派生外观假设，另保留原始材质wrapper及不透明变体。
- 文件几何：器皿源XYZ约14.85×67.5×14.85mm，标准化后14.85×14.85×67.5mm；仪器实际点尺寸约520.5×634.625×435.481mm；候选件各20.4×20.4×29mm。它们不是实测尺寸。V0来源架138×104×22mm、槽15mm/深18mm未替换。
- 仪器安装原点[0.36,0.22,0.74]m、yaw0为场景安装假设。两个候选件中心约[0.2101,0.3676,0.8995]与[0.2101,0.2636,0.8995]m。准确顶点尺寸与规范场景位置见dimensions.csv；每次实际初态另存。
- 新进程5个派生USD全部加载，必要依赖解析，实际视觉顶点最大坐标差约1.8e-16m或0。这只证明变换计算一致，不是源文件/真机精度。器皿和原始OBJ顶点最近距离最大约1.2e-8m，支持来源一致。

![候选部件位置](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/candidate_locations.png)
![源器皿与座截面](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/source_sections.png)

## 配对可行性和负例

两座均按原尺寸检查，采样高度步长0.25mm、数值epsilon0.1微米；这是计算设置，不是真实分辨率。取器皿底部位于座顶下10mm、轴向平行且居中的几何探针姿态，两座均有40个采样截面出现实际边界相交，证据点与高度逐条保存。接近座顶28.5mm高度的中央边界间距约12.6mm，相对器皿外宽的名义总冲突约2.25mm。不同高度有开口、孔或实心底，中央最近边界间距不是“全深度有效孔径”，报告不取全局最小值来概括方孔。
这证明声明姿态/配对存在干涉，不证明所有可能方向、倾角或零件身份都不可能。完整路径的入口、有效装载深度、底面、夹爪净空及盖子避障尚需身份与几何确认，不能用局部相交试验声称完整任务已经判分。
负例把实际源器皿底部放在座顶上5mm，对真实网格做相同截面检查，零相交但位于装载区域外，明确返回geometric_inserted=false及full_success=false；不把“没碰撞”当成功。完整装载独立判分尚未建立/冻结，旧18mm等门槛没有沿用。
新器皿＋V0 15mm装载座仅列为混合配置的名义余量分析，未使用它替代外部仪器目标，也没有隐藏代理孔用于判分。来源架的旧±0.25mm槽内扰动超过75微米余量；新配置预留±0.025mm但尚未运行random，不能据此认为采样合法。

![配对实际网格叠加](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/pairing_sections.png)

## 物理模型和有效性限制

器皿源网格合并重复顶点后884顶点、闭合、面方向一致，材料实体体积约5.0815e-6m³。质量仍假设20g，均匀密度约3935.84kg/m³，不是玻璃实测密度。按闭合空腔壁体积分，质心约[0.000000897,0.000000904,0.029027632]m；主惯量约[1.14570e-6,9.52417e-6,9.52417e-6]kg·m²，主轴与完整张量单独保存。没有复制V0实心外盒惯量。实际PhysX和tensor读回与这些写入值相符，但不构成真实校准。
仪器八个原始实例Mesh逐三角形复制为静态碰撞，保留原开口；部分源仪器/候选件网格不闭合，未使用不可靠的封闭体contains给它们做体积和质量积分。动态器皿最终将源三角形按64径向扇区和3个源倒圆过渡高度带切分，加凸底，共193个凸体。壁起始面排除0.1微米共面底板，避免凸化将内腔填平，未改变源视觉和实物尺寸。
初次自动凸分解23凸体的采样外扩约1.550mm；最终193分块的烹饪表示抽样仍有约0.312mm外扩、1146个漏覆盖样本。PhysX烹饪表示API已实际返回顶点/索引；这不是完整场景actor shape dump，静态Mesh精度也未做全量读回。12000点的抽样误差仅是最大偏差的下界，不是Hausdorff上界。不能把它与75微米余量比较后宣称可用。
本地schema的凸体minThickness默认1mm；本轮显式写0以排查额外加厚，但表示误差没有因此消失，根因未完全确定。未把contact offset当几何膨胀或精度；没有改变rest offset改善孔径。GPU兼容凸体烹饪警告有CPU回退，本轮使用CPU PhysX；不声称支持粒子/软体。
独立源网格顶点与实际姿态审计发现桌面越界约0.28mm。落稳/侧壁结果中的SUBTASK_SUCCESS只是接触、速度和原点高度屏查，不是无穿透或几何精度通过。机器人继承的有效惯量确实与旧USD数值一致；原单位标记与场景不同，其真实/有效尺度依据仍未确认，未随意重建机器人动力学，相关物理真实性结论受限。
完整参数清单见physical_parameters.csv。恢复0、摩擦0.6/0.5、指1.0/0.8、组合average、新体contact/rest=50微米/0、旧架继承100微米/0、CCD和240/60Hz等均区分作者值、配置值和读回项；无法读回的接触偏移/回退材质明确为未知。

![源轮廓与烹饪凸体截面](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/cooked_sections.png)

## 实际运行与数据

| 目录 | 实际结果 | 仿真秒 | run函数墙钟秒 | 解释 |
| --- | --- | --- | --- | --- |
| drop_final01 | SUBTASK_SUCCESS | 4.000000000000093 | 21.08 | 从台面上25mm自由落下并接触落稳；几何精度未通过 |
| side_final01 | SUBTASK_SUCCESS | 4.000000000000093 | 20.23 | 0.4m/s初始化侧向速度；真实侧壁接触峰值约0.357N |
| rack01 | SUBTASK_FAILED | 4.000000000000093 | 18.12 | 新器皿＋旧架持续抖动 |
| grasp_final01 | INITIAL_SUPPORT_INVALID | 1.9999999999999942 | 13.32 | 支撑不合法，2秒处停止进入抓取 |
| grasp_table02 | SUBTASK_FAILED | 28.51666666666537 | 97.48 | 保持子阶段约8.625秒；释放后约90度倾倒，整体失败 |

上述墙钟为run函数内设置/测量/执行时长，不含SimulationApp完整启动关闭，不能当独占GPU性能基准。开始前已有PID491444占显存，未停止。开发grasp01与grasp_table01曾短暂重叠启动/关闭，全部保留且排除性能比较；后续入口增加flock顺序化。没有开展成功率或性能配置比较。
实际动作、双RGB、9维机器人状态、对象位姿、接触点/力/分离量、阶段和时间已保存。H5延续8维动作和学习观测语义，60Hz记录、240Hz逐物理状态，obs/action/next时序审计通过。新的progress只有actual_held列；重叠占位值不可作为测量。所有diagnostic都full_success=false、success=false，不进入完整任务训练索引；未开展ACT/DP训练或完整成功batch验证。
开发失败保留：USD离线schema依赖修复、结果JSON序列化失败、调试截图数值类型修复、早期额外字段长度错误、传感器预热导致初始下落在录制前完成，以及初态窗口包含落稳瞬态。后续修复均有独立新输出；原始文件不覆写。metadata_errata.json纠正旧字段零碰撞误差含义及其他元数据问题。

- [自由下落完整诊断录像](/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_ext01/drop_final01/video/episode_0000.mp4)
- [侧壁接触完整诊断录像](/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_ext01/side_final01/video/episode_0000.mp4)
- [旧架支撑失效与抓取停止录像](/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_ext01/grasp_final01/video/episode_0000.mp4)
- [桌面夹持保持及释放倾倒录像](/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_ext01/grasp_table02/video/episode_0000.mp4)
![夹持保持与失败释放实际轨迹](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/grasp_table02_trace.png)

## 复现入口与记录

准确命令见[运行README](/home/wujing/Desktop/vla/LabSim/demos/lab_cuvette_external/README.md)。新版本独立run.sh已实际运行scene、physics/drop/side/rack/grasp/grasp_table及task/standard/random关口；完整任务关口只记录blocked，不是10/20次完整测试。新配置路径为config/lab_cuvette_loading/V0_ext01.yaml。build.py在已有派生目录时拒绝覆盖，正常查看直接加载交付资产。

## 最少补充信息

优先补充候选座身份与装载方向、器皿和仪器是否配套，以及一组器皿外宽/座限制净宽的测量。其他信息可分步提供，不要求立即完整标定。
| 缺少信息 | 影响步骤 | 当前假设或阻塞 | 最小补充方式 |
| --- | --- | --- | --- |
| 两个候选座各自是什么部件，视频任务使用哪个及哪个方向插入 | 目标身份、装载坐标及可行性 | 两个都保留为候选，不选择隐藏替代座；只分析竖直路径 | 在candidate_locations.png上标1/2并画插入箭头，或给一张内部近照 |
| TestTube_Baked对应器皿型号及与仪器是否配套 | 目标器皿身份与文件配对 | 仅确认几何与包内OBJ一致；不认定同型号 | 器皿照片/型号及是否配套的一句确认 |
| 源模型单位依据及原始CAD/STEP或厂家尺寸资料 | 文件尺度与真实器材的关系 | 按USD声明单位保持原物理尺寸；不做真实准确性结论 | 有则提供原STEP或一项已知尺寸即可先核对尺度 |
| 器皿外宽、高、底厚、壁厚和质量 | 几何余量、质量惯量和抓取点 | 14.85×14.85×67.5mm为文件几何；20g假设；惯量按网格均匀质量积分 | 先给卡尺外宽与高度、称重；壁/底厚后补 |
| 实际入口、限制净宽、有效深度、支撑面和装载方向 | 完整装载路径及独立判分 | 候选截面约12.6mm只适用于部分高度和方向；完整装载未放行 | 一张带方向标记的近照＋限制位置净宽测量 |
| 真实来源架孔宽、深度和配合关系 | 合法初态与从架抓取 | 未替换的15mm V0孔只余约75um，实际抖动 | 一项孔宽测量和是否可放入该器皿的确认 |

## 证据索引

- [source_manifest.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/source_manifest.json)
- [asset_roles.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/asset_roles.json)
- [conversion.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/conversion.json)
- [dimensions.csv](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/dimensions.csv)
- [independent_load_validation.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/independent_load_validation.json)
- [feasibility.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/feasibility.json)
- [vessel_mass_properties.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/vessel_mass_properties.json)
- [physical_parameters.csv](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/physical_parameters.csv)
- [diagnostic_audit.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/diagnostic_audit.json)
- [attempt_inventory.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/attempt_inventory.json)
- [metadata_errata.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/metadata_errata.json)
- [baseline_before.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/baseline_before.json)
- [baseline_after.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/baseline_after.json)
- [archive_integrity_after.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/archive_integrity_after.json)
- [environment.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/environment.json)
- [stage_status.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/stage_status.json)
- [questions.json](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext01/questions.json)
