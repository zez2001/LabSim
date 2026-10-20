# LabSim V0 demo02 视频场景恢复与装载关口核查

日期：2026-10-20。项目 `/home/wujing/Desktop/vla/LabSim`；新分支 `codex/lab-cuvette-demo02`，从 `2ee29b451f830d9d0af65560a543185c97539077` 派生。最终代码提交与远端验证以本轮阅读包版本记录为准。

**完整装载 demo 本轮尚未完成。** 本轮已经重新检查原视频/四张照片、全部相关本机附件、源 USD 实例和材料子集，生成保留源尺寸的 V0_demo02 仪器派生资产，实际用现有Isaac渲染四个静态审核视角，修正判分语义并检查采集/过滤接口。白色完整架体的 CAD 仍未找到；两内部座真实身份未确认，当前原器皿与原座的居中直立路径有实际表面相交。未用机外目标、单槽支撑、缩模、删墙或放宽穿透门槛替代本轮目标。

## 1 原视频中究竟是什么场景

原视频为 3840×1080 双视角、143 帧、2.4 fps、59.584 s；编码时间不是机器人控制时钟。4 张原照片和精确提帧的文件哈希见 [媒体清单](reference_review/source_media_manifest.json)，完整观看依据见 [原媒体核查](reference_review/reference_review.md)。

- 完整白色来源架经帧 0 广角与帧 36 手相机两次独立计数，为 **6×6，36 个顶面开口**。旧 V0 的 6×8 是合成实现选择。本轮没有沿用它。
- 目标从近角槽取出，远角附近蓝色器皿留下。图像可确认至少两件来源器皿，不能给出孔距、壁厚、槽深或底厚。
- 广角同时有两台开盖仪器。实际装载的是左前景仪器，后侧右方另一台属于邻近场景；手相机初始帧主要朝向后者，不能把它的内部零件误映射成最终目标。
- 目标位在前景仪器打开盖板后的黑色腔内。按最终手相机图像称它为 A：右下方、距铰链较远的金属框座。B 在左下方较近铰链，已有透明/粉色方杯状物。视频不能确认其厂家功能名。

![原视频场景角色](reference_review/frames/wide_scene_roles_frame_000.jpg)

![完整架体的另一视角](reference_review/frames/source_rack_t15_hand_crop.jpg)

![腔内A/B及实际松爪](reference_review/frames/chamber_identity_frame_142.jpg)

本轮流程要求仍为 `RESET → APPROACH_SOURCE → GRASP → EXTRACT → TRANSPORT → ALIGN → INSERT → SUPPORT_TRANSFER → OPEN → RETREAT → VERIFY`；不新增关盖、测量或回收。视频能显示运动及末段松爪，不能证明真实支撑力、无穿透或撤离后持续 3 s 稳定。

## 2 资产对应和深层检查

首轮递归清单覆盖 Desktop、Downloads、Documents、`.codex/attachments` 中 76,930 个普通文件，其中2,503个模型、48个归档，见[附件清单](source_audit/delivery_inventory.json)。随后[不按文件名筛选的追加核查](source_audit/additional_delivery_check.json)检查49个归档（含本轮新建草稿归档）的131个CAD成员，53个内容哈希均对应已知文件或本轮草稿；5个潜在外部模型内容身份实际打开后仍无完整来源架。模型文件是递归枚举、按来源分类，并非全部深读。结论仅覆盖所列本机范围，不排除未传输文件。

`newnew4.usd` 用 LoadAll 打开：普通 active Traverse 为 0 个 Mesh；instance proxy 遍历得到 8 个实际实例网格；TraverseAll 可读到 6 个抽象 prototype 网格。原型与实例不能相加为 14 个部件。激活、可见性、purpose、reference、payload 和材料子集均逐项核对；未找到隐藏多孔架。机身侧面的密集通风孔不是白色来源架。详见 [USD 深层检查](source_audit/usd_deep_inspection.json)。

| 实物角色 | 原文件/原网格 | 派生资产及本轮实例 | 结论 |
|---|---|---|---|
| 器皿 | `TestTube_Baked.usd`，`/TestTube/Mesh` | ext02 `walls28_mm.usda`；`/World/VesselPreview` | 复用真实文件外形和28块碰撞；本轮仅无支撑静态预览，不是来源槽合法初态 |
| 白色完整多孔架 | 当前附件中未找到 | `/World/SourceRackUnavailable` 仅空Xform | 6×6 是图像计数；没有把代理架改名成原CAD架 |
| 机身 | `newnew4.usd` 的 `tn__1_ZBFi3j3/...tn__1_x1ZBa0c2t04z0ZA6/Mesh` | `video_pose_verified/instrument_native.usda`；`/World/Instrument/Visual/Source/...` | 原主体合并网格保留，不缩放尺寸 |
| 盖板 | `tn__3_ZBFi3j3/...tn__8_x1iBOa1g0Jv0g7n4/Mesh` | 同上，派生层绕估计铰链刚体旋转 | 源保持不变；视频近竖直是图像估计 |
| 黑色样品腔 | 机身合并网格内凹区域 | `/World/Instrument/TaskFrames/chamber_survey` 为参考帧 | 没有独立 chamber 网格；参考帧不是承托面 |
| 内座 A 暂定 | `tn__2_ZBFi3j3/...tn__4_x1iBOa1g0Jv0g7n4/Mesh` | `candidate_far_hinge`；源座全部保留 | 距铰链较远，暂定对应视频 A；身份未确认 |
| 内座 B 暂定 | `tn__2_1_dNPo5b5/...tn__4_x1iBOa1g0Jv0g7n4/Mesh` | `candidate_near_hinge`；源座全部保留 | 与 A 为同一 prototype，未删除中央材料体 |
| 邻近第二仪器 | 复用同一完整仪器 CAD | `/World/NeighborInstrument` | 视频存在第二台；工程布置，型号与相对位姿未标定 |
| 机器人 | 既有 `assets/robots/Franka.usd` | `/World/Franka` | 继续作为视频白色机械臂代理，未校准实物动力学 |

[资产对应 CSV](asset_correspondence.csv) 与 [JSON](asset_correspondence.json) 给出完整原 prim、64 位原/派生文件 SHA256、实际场景路径及逐网格变换误差。主 CAD SHA256 为 `8261714be7250b61466e9b3537a25438a5cc441c20a465ea6b3c27b43383a1dc`；源器皿 Baked SHA256 为 `c7d6897a1e555c282ac30a53e95cb872fda4e112821d2a013a9612bd40e39f36`。

两座 CAD 都是单一白色 metallic 框体，不含不同透明器皿的独立材料子集。视频 B 上的透明物身份未知；不能把座的中央壁当成已装器皿删掉后宣称配合成功。

## 3 单位、尺寸和累计变换

全部 CAD 数值来自本轮实际网格顶点和完整祖先变换，**实物值均未测量**。详细源数据见 [尺寸表](source_audit/dimensions.csv)、[原网格测量](source_audit/source_geometry.json)、[最终场景测量](asset_correspondence.json)。表中毫米小数仅保留审计结果，不代表真实精度。

| 项目 | 原文件完整变换后的尺寸 mm | 标准化源姿态 mm | 最终静态场景 mm/状态 |
|---|---|---|---|
| 器皿外包络 X×Y×高 | Y-up源转Z-up后 14.850006×14.850006×67.499995 | 相同 | 相同；底部最低点为局部 Z=0 |
| 器皿底部区域 | Z<0.3 mm 顶点覆盖 X/Y 各约±7.425003 mm | 相同原网格 | 这是顶点区域包络，非完整承托面积证明 |
| 抓取位置 | 实物未知 | 继承底部上方53 mm工程值 | 需对完整架体和夹指净空重新验证；本轮未抓取 |
| 完整来源架 | 未找到CAD | 行列仅有图像6×6依据 | 总尺寸、孔距、槽宽/深、壁/底厚、露出高度均未知 |
| 仪器机身主网格 | 520.5×630.0×230.0 | 相同 | 相同，不把机身高度写成开盖总高 |
| 源开盖整体总装 | 520.5×634.624772×435.480987 | 相同 | 近竖直派生姿态整体 520.5×630.0×576.999999 |
| 源盖板网格AABB | 148.0×382.237888×223.466628 | 相同 | 刚体改姿态后AABB 148.0×217.429619×368.999992；不是几何缩放 |
| 两候选座各自外包络 | 20.4×20.4×29.0 | 相同 | 相同；中心间距104 mm |
| 两座局部高度 | 底部包络Z145、顶部Z174 mm | 中央竖直射线表面Z145/147 mm | 世界底部包络0.885 m、顶部0.914 m；中央承托射线0.887 m，不能代替整个底面承托证明 |
| 腔体Z200 mm局部截面 | 外局部轮廓153×316；内轮廓约140×286 | 相同 | 仅一个水平截面，不是全腔或整只手爪路径净空 |
| 候选入口及全深限制 | Z173.5 mm中央X/Y边界间距约12.6 | 沿座高每0.25 mm保存116个截面 | 中部侧面开窗，并非全深封闭方孔；原器皿声明姿态仍相交 |

仪器原文件单位 `0.001 m`、Z-up，`/RotatedRoot` 已有 +90° X 旋转；代码先取完整变换，再一次性作毫米转米与原点归一化。没有再叠一次90°。器皿 Baked 文件为米、Y-up，只转为Z-up一次。151 B 的旧入口 `TestTube_629.usd` 指向 `/root/LabUtopia/shiguan629/test/试管.obj`，当前读取权限不允许核实该绝对依赖；本轮使用有实际几何的 Baked/包内 OBJ，未把不完整入口当作独立资产。

盖板采用三角面法线按面积聚类，主面源角为 **41.566965°**，不是 AABB 对角或全网格 PCA 的角度。派生层绕两铰链几何中心连线估计的 X 轴，增转 **+48.433035°** 得到90°工程对照姿态；90°来自原视频近竖直外观估计，未作相机/铰链实测标定。源文件、盖板网格尺寸和其它部件不改。`source_pose` 对照与 `video_pose_verified` 派生目录分别保留。

主仪器 world平移 `[0.36,0.18,0.74] m`，yaw=0；邻仪器 `[0.96,0.53,0.74] m`。这些是用于审核的工程位置，不是从视频标定的绝对坐标。变换链为 `World → Instrument → TaskFrames/chamber_survey → candidate_far_hinge/near_hinge`。chamber参考原点在机身坐标 `[-149.915536,95.629353,145] mm`；两座参考帧相对其Y为±52 mm。A/B真实目标身份未确定，因此正式 `selected_target_seat_id=null`，参考帧不能冒充已验收目标。

源点经声明的单位/姿态/世界变换后，与最终主/邻仪器视觉网格逐点差异最大约 `4.88×10⁻¹⁶ m`；这只说明变换数值对应正确，不是物理或真实精度。盖板有意刚体改姿态带来的最大点位移约317.675 mm另行记录，不混为误差。

视觉与碰撞分离。仪器8个原实例三角网格逐一对应独立静态碰撞输入，不用填平内腔的整机凸包；实际读回核对原面索引相同；视觉与碰撞输入对应顶点最大差约 `2.944×10⁻⁸ m`（0.02944 μm，float点存储量化），不是构造器名义“0误差”的直接照抄。**本轮尚无完整 PhysX cooked几何读回，不声称已经排除运行穿透或证明整只手爪安全。**

实际盖板/入口剖面对照另见下图：原41.566965°盖板会遮挡两个座的竖直中心轴；派生近90°姿态后，较远A轴的盖板遮挡消失，但近B轴仍可与上部曲面/翻边相交。这是局部三角面几何核查，不能据单轴射线宣布整只手爪有净空。A/B身份、原座入口与器皿冲突仍未解决。

![源盖姿态与视频估计姿态对照](source_audit/lid_source_vs_video_pose_sections.png)

完整源姿态与最终场景的逐点、逐面索引比较、主/邻两套装配、世界坐标和中心射线见 [最终场景核查](source_audit/final_scene_verification.json)。

![两座实际几何](source_audit/candidate_three_views.png)

![原配声明姿态的相交见证](source_audit/candidate_original_pair_sections.png)

## 4 为什么不能开始成功轨迹或重复批次

本轮首先核对了部件、单位、朝向和装配，再做配合剖面。两座都是原金属框，顶部中央X/Y边界间距约12.6 mm；器皿外宽约14.85 mm。针对明确声明的居中、竖直、yaw=0、从座口下插10 mm姿态，实际三角面剖面在 **40个采样高度**出现边界交叉，两个候选都得到同样见证。116个全高截面及交点坐标保存在 [全深度证据](source_audit/candidate_fit_and_chamber_sections.json) 和 [截面CSV](source_audit/candidate_full_depth_sections.csv)。

这不是简单按14.85>12.6数值给任务失败标签，也不是断言所有可能姿态都不可插。它是当前声明路径实际材料体相交的证据。未搜索无依据的倾角路径，未将孔扩大、器皿缩小、碰撞体缩小、墙体删除或关闭碰撞来制造成功。

样品腔确在机身内。两座中心竖直射线上，没有检测到高于座口的额外机身平面；这排除了“这两条轴被额外body平面封住”的局部疑点，不能排除整只器皿、手爪、盖板或烹饪几何的所有冲突。完整架体缺失又使来源槽自然支撑、夹指进入与拔出净空无法验收。

因此本轮正确新场景的自然落稳、架内抓取、拔出、搬运、腔口进入、内部插入、交接、松爪、撤离与稳定观察均未执行；也未开展标准5次或跨槽/布局随机10次。先前 demo01 的机外工装5/5和2/3不属于demo02，不能继承为本轮成功。

## 5 判分和采集接口实际修正

新增 `demos/lab_cuvette_demo02/analyze.py`、`collector.py`、`data_check.py`，继续使用现有 collector 与 `MinimalPickDataset`，不另建训练框架。[数据核查说明](data_audit/README.md) 和 [最终接口检查](data_audit/collector_interface_final_checks.json) 记录了实际执行范围。

- 独立判分分别要求来源槽合法支撑和清出、正确腔内目标装载、承重交接、双指打开脱离、独立撤离净空、撤离后3 s稳定、原50 μm穿透门槛、有效接触/姿态和无非法绑定。控制器进入末阶段不等于成功。
- 场景对应、workflow_success、native_pair_success、real_calibrated、data_eligible分别记录。静态外观对应不能自动打开任何成功或训练资格。
- 只读回算历史 seed7000：实际停在 OPEN、46.233333 s，峰值源几何穿透50.289093 μm，原50 μm门槛不变。原评分和H5保留；新sidecar将末3 s标为 `terminal_window`，`post_retreat_window.status=unavailable`，`stable_after_retreat=null`，`actual_retreat_clearance_m=null`。不能把中止前最后窗口叫撤离后观察。
- 即使日志写了 VERIFY，只要独立整手净空缺测或不足，仍不能产生合格post_retreat窗口；不足3 s时稳定结果也为null。[实际历史反例检查](data_audit/semantic_final_clearance_checks.json) 已执行。
- 原生速度、USD原始速度和位姿/COM差分均保留，同步按相邻物理时刻分析；第一个差分不可用，不补零。历史seed7000最大线/角差异约0.23554 m/s、11.9691 rad/s，作为告警保留；非有限值和实际异常运动仍是硬关口，不将有限的两路差异作为永久松爪前阻塞。

新任务元数据包括槽位ID、目标座ID、资产清单哈希、十一阶段、双路RGB、机器人状态、物体状态与接触。动作语义为7个机械臂绝对关节目标（rad）加1个对称手指位置目标（m）；观测在动作前、next_state在显式物理子步后。未知槽位或座位不写假ID。

终止采集需同时绑定同episode、资产、槽位、末时刻、physics/events哈希和新独立评分。索引只用外链读取原H5；旧工程演示、失败、缺独立证据或机外目标均被拒绝。元数据接口正反例均通过，但没有制造成功H5。

本轮实际用历史H5检查数组与观测—动作对齐，并对空新任务索引调用原加载器，返回 **`Dataset contains no complete successful episodes`**，eligible_count=0。**这次是正确拒绝的接口检查，未读出新任务成功训练batch，也不是已经完成数据验收。** 观测时间戳检查不等于相机曝光/延迟标定。完整原H5和逐步数据保留在本机，精简阅读包只含必要证据。

## 6 已执行、未执行和静态审核状态

| 项目 | 本轮实际状态 |
|---|---|
| 原四照片、视频关键双视角及来源架计数 | 已实际查看并保存逐帧/哈希证据 |
| 原附件、ZIP成员、实例、材料、几何及变换核查 | 已运行离线审计，未找到白架，保留原配冲突 |
| 新派生仪器、场景USD保存与离线重载、实际顶点比对 | 已完成；新目录独立，8部件均保留 |
| Isaac静态相机截图 | static_review_04已实际完成4个1920×1080视角；物理时钟0→0、无World.reset、请求物理步0 |
| 新场景物理步进、接触/支撑及完整状态机 | 未执行，静态关口未通过 |
| 新场景完整连续视频、标准5次、随机10次 | 未执行，无新成功率 |
| 新任务采集结构/判分语义/过滤拒绝检查 | 已执行元数据与历史记录检查 |
| 新任务完整成功H5和一个成功训练batch | 未完成，无可用新成功样例 |
| 真实型号确认、实物尺寸与动力学标定 | 未完成 |

静态场景中器皿初态在候选座口上方20 mm，明确标为 **unsupported preview**，不是架内来源姿态。正式静态审核来自 `outputs/lab_cuvette_loading/V0_demo02/static_review_04`：[result.json](static_review/result.json) 记录物理时钟0→0、预览位移0、未调用World.reset、请求物理步0。这是USD组合/渲染验证，不能用静止画面声称自然支撑。早期static_review_01未产图、02含reset初始化，不作为最终零步证据。整手与架、盖板、腔壁的连续碰撞/可达性仍未验证。

[俯视](static_review/top.png)、[侧视](static_review/side.png)、[参考视角](static_review/reference.png)、[腔内近景](static_review/chamber.png) 均有静态/缺架/原配未通过标注。

![新USD静态参考视角，非连续任务](static_review/reference.png)

![腔内原座及无支撑器皿预览](static_review/chamber.png)

[acceptance.json](acceptance.json) 保留三个静态阻塞及分离的成功/校准/数据资格；[workflow_gate_result.json](workflow_gate_result.json) 是实际请求完整任务入口的返回：`BLOCKED_STATIC_ACCEPTANCE`，phases_executed为空，标准0/5、随机0/10，没有新物理轨迹、post_retreat unavailable、stable_after_retreat=null。

V0、ext01、ext02、demo01及seed7000原始失败均保留；本轮新增目录独立，本轮保护哈希实测覆盖6067个旧文件，修改、缺失和inode变化均为0，见 [保护检查](preservation.json)。未升级环境、迁移物理后端或开展训练/大规模参数搜索。原版本诊断阈值没有放宽。

## 7 准确复现入口

以下从仓库根执行，输出目录必须换成未存在的新目录。离线审计复用已有USD/Python环境，静态图使用现有Isaac，不是新的物理任务运行命令。

```bash
cd /home/wujing/Desktop/vla/LabSim

# 重新审计原始附件/原USD，输出独立证据目录
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo02.audit_sources \
  --output outputs/lab_cuvette_loading/V0_demo02/source_audit_new

# 加载已保存的新场景，生成静态多视角图；不推进任务物理时间
bash demos/lab_cuvette_demo02/run.sh --headless --review \
  --scene assets/lab_cuvette_loading/V0_demo02/video_pose_verified/scene_review.usda \
  --output outputs/lab_cuvette_loading/V0_demo02/static_review_new

# GUI静态审核：省略--headless，同样不是物理任务
bash demos/lab_cuvette_demo02/run.sh --review \
  --output outputs/lab_cuvette_loading/V0_demo02/gui_review_new

# 申请完整任务时，当前静态关口未通过，入口明确返回BLOCKED_STATIC_ACCEPTANCE
bash demos/lab_cuvette_demo02/run.sh \
  --output outputs/lab_cuvette_loading/V0_demo02/workflow_gate_new

# 只读回算历史失败语义，不改变原episode
../labutopia-env/bin/python -m demos.lab_cuvette_demo02.analyze \
  outputs/lab_cuvette_loading/V0_demo01/random3_20261019/seed_7000/trial_00 \
  --historical --output /tmp/demo02_seed7000_semantics_new.json

# 对当前无新成功episode状态，验证原加载器明确拒绝
../labutopia-env/bin/python -m demos.lab_cuvette_demo02.data_check \
  --output outputs/lab_cuvette_loading/V0_demo02/data_index_new
```

配置为 `config/lab_cuvette_loading/V0_demo02/native_scene.yaml`。离线派生生成器为 `demos/lab_cuvette_demo02/build_scene.py`；源姿态对照使用 `--source-pose`，近竖直视频对照为默认。生成器将资产及manifest写入指定的新目录，拒绝覆盖已有目录；本轮scene_build文档是单独保存的交付快照。正式物理执行器的架内抓取、完整碰撞路径和内座装载适配尚未完成，不能把门控入口说成已实现整条操作。

本轮配置声明240 Hz物理、60 Hz控制、TGS64/1、contact_offset=50 μm/rest_offset=0、摩擦0.6/0.5、恢复0，沿用既有释放观察参数；这些是候选工程配置，**本轮未通过新任务运行验证，更不是真实测量**。原始Franka、器皿质量/惯量/材质和速度两路差异均未真实标定。

## 8 三项关键阻塞与集中补件

1. **完整架体未找到。** 请给准确CAD文件/装配入口；或可追溯图纸/测量，包括6×6槽位方向、总尺寸、孔距、槽宽/深、壁/底厚和露出高度。图像计数不能提供这些几何。
2. **内部座和型号配套未确认。** 请在视频/CAD截图标明A、B的真实功能、实际插入方向及器皿/仪器/座的型号关系。距铰链的暂定对应不能代替身份确认。
3. **原配声明路径存在几何冲突。** 请提供器皿全轮廓与座入口/全深限制、承托高度和公差的厂家或实测依据；如CAD错误，明确修订部位及依据，同时补充实际开盖角度/铰链依据。缺少这些资料不应随意缩模或删座。 集中机器可读信息见 [补件清单](required_information.json)。
