# Project_v1_1 新报告骨架与收口检查

日期：2026-10-27。本文是结构和证据计划，不是最终发布报告。fine_preinsert_02仍待闭合结果；新版本teacher回归、GPT抓持/完整任务、冻结formal5和最终同提交复现均未由本文宣告完成。此处不生成DOCX、不切换默认阅读包清单。

## 已核对的要求

来源为本轮Project_v1_1任务指令（ed19ec81-b7b6-4f47-87d1-41d778e17281）。核心目标仍是GPT从standard reset连续完成抓取、搬运、原A座插入、支撑交接、开爪、退让及至少3秒独立稳定。禁止teacher接管、任务宏、隐藏物体真值；不启动训练，不重采历史20+20。

必须区分诊断与任务：原异常前缀、自由空间、微位移、手工抓持短移是控制诊断。Project_v1_1/grasp_transport_02完成17条诊断、物体短移27.808 mm且grasp_success=true，但完整transport门槛仍未触发，完整装载没有执行。fine01的24项微位移满足接口1 mm容差，但100 µm诊断目标为0/24，不能用宽容差宣称达到精细对准预算。fine02尚待实际数据。

相机new_initial_view是实际闭合诊断录像解码与机器人TCP离线标记，并非模型实际收到的JPEG；mount_v2_cpu_projection只是CPU建议，尚未渲染。不能将投影在画内或TCP居中等同操作主体可见。最终需逐阶段实际模型输入、标定、预处理和JPEG SHA证据。

## 建议正文六部分

1. **当前结果与五个问题**：动作执行可靠性、视觉可观测性、稳定持物/搬运、完整装载、未解决最远阶段。每项只写已闭合证据；CPU、诊断和GPT任务分列。
2. **末端异常根因和修复前后**：同原始前缀的请求/实际轨迹、固定目标、IK连续种子、实际关节与TCP、逐时误差；free-space两姿态/正负轴/TCP朝向/小旋转/wait/gripper覆盖、缺失探针与timeout均列明。fine01与fine02给min/median/P95/max、100 µm达标数和保持漂移，明确endpoint/path采样范围，保留失败基线。
3. **相机与模型输入**：新挂点版本、K/外参/时间戳、原生分辨率到实际模型图像的变换；至少初态、闭合、离架、搬运、预插入、插入支撑、开爪撤离的真实输入。CPU投影建议与已渲染/已发送输入分开；512×384 low与清晰候选只有真实比较后才能冻结。
4. **通用接触保持与实际诊断**：9.394→10.460 mm回张反例、no-reopen/连续确认/失触慢闭/显式释放规则，力cap与实测力分开；当前A/B 5093个接触前样本相同、实际力/轴向滑移/27.808 mm物体短移。相对µm指标仅为仿真记录，不写平台精度；两run均非完整装载。
5. **GPT实际运行与冻结评测**：沿原provider和ledger，保留每次debug/正式请求、动作、输入、原始null及failure domain。完整成功后冻结模型/prompt/图像/工具/控制/安全/评分再正式5次；重复控制问题应回到确定性诊断，不能跑完5次失败便收口。共享30美元/1500请求预算包含前轮占用，估计、未知usage预留与实付区分。
6. **回归、使用与发布**：新teacher5、closed H5/ACT/DP重新读取、同发布代码的clean checkout与独立asset cache、GUI/headless/reset、完整连续媒体QA、实际模型输入、最终代码/控制/相机/scorer/HF pins/CI与命令。无第二台机器时准确写同机范围，继续完成其余项。

正文可约6–8页，完整SHA/逐集表/全部输入与来源留在小证据JSON/CSV。最终DOCX按documents skill执行首次marker、bundled authoring、逐页render QA；本骨架不执行marker或创建DOCX。

## 必须闭合的发布门槛

- fine02实际闭合并与fine01按同定义比较，未过目标时继续诊断，不改验收阈值。
- 相机真实关键阶段输入验收完成，清晰度/延迟/费用比较后冻结。
- GPT先独立稳定抓取及搬运，再完整成功；正式5必须在完整成功后以固定配置开始。
- 本轮涉及新共享控制/评分逻辑，应做本版本teacher 5次standard完整回归。旧Project_v1的已有5次不算本次回归。
- 最终发布代码上完成干净checkout、独立缓存、实际teacher/GPT和closed数据读取。运行commit、控制依赖指纹与交付commit分列；不能把源码等价自动写成同一SHA验收。
- 提交推送origin/codex/labsim，核对remote SHA与对应CI；报告中不预填未来提交。最终阅读包脚本自动记录生成时真实HEAD，发行清单记录各实际运行身份。

## 现有脚本审查

目前没有独立Project_v1_1最终report builder或最终package manifest。旧Project_v1/report/generate_report.py硬编码旧assets/sample证据及恰好5个旧formal输入，不能只替换标题后当新报告。Env_v1/report/render_docx_isolated.py仍可作为既有只读源、无网络/无GPU渲染器使用。

scripts/package_agent_results.py可复用：严格源路径、拒绝symlink/LFS指针/重复目标/覆盖、写源与成品SHA、保留相对链接。它**不强制**clean/push/remote CI已通过；这些必须由外部发布步骤核实。默认docs/agent_handoff/package.json仍指向Project_v1，本轮不可直接沿默认打包。

第一阅读说明只进行占位符替换，不经过普通Markdown的link重定位，因此新first-read必须按包内目标路径写链接。DOCX链接也不由打包脚本重写，作者阶段必须保持Project_v1_1/report与media/evidence相对层级。未复制的Markdown引用会转GitHub固定SHA链接，须确保被引用路径在该提交真实受追踪，不能链接到只在本机存在的ignored输出。

## 严格current-only包原则

使用独立Project_v1_1 manifest，逐文件allowlist；不整包选择Project_v1、整个agent_handoff或整个diagnostics。历史HF资产/sample与旧Project_v1结果以固定revision/commit链接引用，不重复复制旧大视频、旧报告、旧teacher样例。当前A/B、原异常新复现和fine失败基线属于本轮证据，可选择关键图与小表。

建议20 MiB以内：新报告DOCX/MD与build/QA、当前usage/配置/lock/policy、必要的控制/接触/视觉图表、最后真实GPT全流程连续视频及一个代表失败、当轮teacher回归汇总和一条必要连续视频、全部formal5结果/预算/评分小证据、closed reader与final checkout/CI/source保护清单。完整原H5、gzip raw、全工程/环境/权重/检查点、凭据与API key均不进入包；完整源项目通过GitHub取得。

当前可选文件及待实际闭合后再添加的必需证据见current_only_package_plan_20261027.json。该JSON不是可执行最终manifest，不允许凭它把未完成结果打包为发布。

## 当前CPU与保护结果

按现有workflow测试选择：contracts346 passed/11 skip记录，reader22 passed/0 skip；两环境合并368个具体用例全部至少通过一次，所有依赖skip范围补齐。reader使用现有CUDA-disabled runtime，部分版本与CI CPU wheel不同，所以不是最终remote CI。详见validation/cpu_regression_20261027/summary.json与runtime_versions.json。

相对f94f945，旧配置18、独立实现40、受追踪资产596、旧发布证据880条均无Git变更，107个USD来源条目亦无变更。shared factory/CLI/reader/Cubence扩展已逐项分类；共享runner源码SHA会影响controller指纹，旧结果不自动等价于新运行。5份闭合归档审计只证明各自256个局部非raw文件在该归档操作前后不变；历史大输出无全局before快照，无法完整核验，不能扩展结论。
