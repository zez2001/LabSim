"""Assemble traceable delivery from saved results; does not run simulation."""
from pathlib import Path
import json,csv,hashlib,subprocess
ROOT=Path(__file__).resolve().parents[2];DOC=ROOT/'docs/lab_cuvette_loading/V0_ext01';OUT=ROOT/'outputs/lab_cuvette_loading/V0_ext01'
def load(path):return json.loads(Path(path).read_text())
def save(name,data):(DOC/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+['| '+' | '.join(str(x).replace('\n','<br>').replace('|','/') for x in row)+' |' for row in rows])
def link(label,path):return f'[{label}]({Path(path).resolve()})'

def main():
    src=load(DOC/'source_manifest.json');geo=load(DOC/'source_geometry.json');conv=load(DOC/'conversion.json');mass=load(DOC/'vessel_mass_properties.json');audit=load(DOC/'diagnostic_audit.json');preserve=load(DOC/'baseline_after.json');valid=load(DOC/'independent_load_validation.json');feasible=load(DOC/'feasibility.json');roles=load(DOC/'asset_roles.json');cook=load(OUT/'drop_final01/cooked_comparison.json')
    status=[
        dict(item='加载成功',state='passed',evidence=['independent_load_validation.json','outputs scene_attempt01/scene.usda'],limits='五个派生USD独立加载；必要引用已解析；不代表物理通过'),
        dict(item='几何接入验收',state='coordinate_geometry_passed_with_identity_limits',evidence=['conversion.json','dimensions.csv','source_sections.png'],limits='单位/朝向/defaultPrim/实际顶点尺寸通过；源模型真实尺寸及身份未确认'),
        dict(item='配对装载可行性',state='blocked_identity_and_geometry',evidence=['feasibility.json','pairing_sections.png'],limits='两候选座给定居中竖直姿态有网格边界相交；其他方向未穷举；身份未知'),
        dict(item='物理配置及限定检查',state='partially_observed_NOT_accepted_for_precision',evidence=['vessel_mass_properties.json','drop_final01/runtime_readback.json','cooked_sections.png','diagnostic_audit.json'],limits='质量惯量读回及落稳/侧壁接触有证据；烹饪偏差约0.312mm，源几何桌面越界约0.28mm；旧架抖动；机器人惯量未校准'),
        dict(item='子任务',state='grasp_hold_phase_passed_release_failed',evidence=['grasp_table02/physics_records.json','grasp_table02/video/episode_0000.mp4'],limits='桌面局部诊断；双指抬升保持约8.625s，最后释放倾倒，整条诊断失败'),
        dict(item='完整任务',state='not_executed_blocked',evidence=['task_gate01/gate_result.json'],limits='没有完整任务执行器放行；新装载判据未冻结；完整成功0'),
        dict(item='standard和random',state='blocked_0_full_episodes',evidence=['standard_gate01/gate_result.json','random_gate01/gate_result.json'],limits='仅运行关口；未开展10次/20次完整批次；随机种子5000至5019已保存'),
        dict(item='真实一致性',state='not_verified',evidence=['config calibrated=false'],limits='未做真实尺寸/材料/机器人/相机校准或real2sim gap评估')]
    save('stage_status.json',status)
    questions=[
        dict(missing='两个候选座各自是什么部件，视频任务使用哪个及哪个方向插入',affects='目标身份、装载坐标及可行性',current='两个都保留为候选，不选择隐藏替代座；只分析竖直路径',minimum='在candidate_locations.png上标1/2并画插入箭头，或给一张内部近照'),
        dict(missing='TestTube_Baked对应器皿型号及与仪器是否配套',affects='目标器皿身份与文件配对',current='仅确认几何与包内OBJ一致；不认定同型号',minimum='器皿照片/型号及是否配套的一句确认'),
        dict(missing='源模型单位依据及原始CAD/STEP或厂家尺寸资料',affects='文件尺度与真实器材的关系',current='按USD声明单位保持原物理尺寸；不做真实准确性结论',minimum='有则提供原STEP或一项已知尺寸即可先核对尺度'),
        dict(missing='器皿外宽、高、底厚、壁厚和质量',affects='几何余量、质量惯量和抓取点',current='14.85×14.85×67.5mm为文件几何；20g假设；惯量按网格均匀质量积分',minimum='先给卡尺外宽与高度、称重；壁/底厚后补'),
        dict(missing='实际入口、限制净宽、有效深度、支撑面和装载方向',affects='完整装载路径及独立判分',current='候选截面约12.6mm只适用于部分高度和方向；完整装载未放行',minimum='一张带方向标记的近照＋限制位置净宽测量'),
        dict(missing='真实来源架孔宽、深度和配合关系',affects='合法初态与从架抓取',current='未替换的15mm V0孔只余约75um，实际抖动',minimum='一项孔宽测量和是否可放入该器皿的确认')]
    save('questions.json',questions)
    parameters=[
        ['mass',.02,'kg','器皿','本轮可配置假设','config vessel.mass_kg','PhysX mass query及tensor读回','否'],
        ['COM',mass['center_of_mass_m'],'m','器皿','源闭合网格＋均匀质量分布计算','derived MassAPI','tensor com及PhysX查询','否'],
        ['inertia',mass['principal_inertia_kg_m2'],'kg m^2','器皿','源闭合壁/底积分，非V0实心盒','derived diagonalInertia＋principalAxes','tensor完整惯量及主惯量读回','否'],
        ['friction','0.6 static / 0.5 dynamic','1','器皿/外部仪器','可配置假设','MaterialAPI','绑定路径读回；数值作者层，非完整运行时材质读回','否'],
        ['finger friction','1.0 / 0.8','1','指端','可配置假设','run.py FingerPhysics','作者层＋绑定','否'],
        ['restitution',0,'1','新器皿/仪器/指端','可配置假设','MaterialAPI','作者层','否'],
        ['combine','average / average','token','新物理材质','本轮选择','PhysxMaterialAPI','作者层','否'],
        ['contact/rest offset','0.00005 / 0','m','新器皿/仪器/机器人','可配置数值设置','PhysxCollisionAPI','USD写入；未直接运行时读回','否'],
        ['rack contact/rest','0.0001 / 0','m','来源架','V0源资产继承','复制rack USD','源文件相同SHA及独立inode','否'],
        ['convex minThickness',0,'m','分块凸体','取消额外加厚的源几何保真尝试','PhysxConvexHullCollisionAPI','写入0，烹饪误差仍未解决；不据此宣称有效厚度精确','否'],
        ['CCD',True,'bool','新器皿及场景','本轮选择','Physx APIs','场景作者层/读回；器皿作者层','否'],
        ['step/control','240 / 60','Hz','场景','沿用工程控制频率','World和cfg','时序及engine时钟对照，4子步','否'],
        ['solver/iterations','CPU TGS 64/16','token','场景/刚体/关节','工程选择','PhysxScene/RigidBody/Articulation','后端/solver读回；迭代作者层','否'],
        ['Franka dynamics','旧USD质量/质心/惯量','mixed','机器人','源资产继承，原始依据未知','旧Franka USD','选取连杆/手/指实际质量惯量读回，尺度仍待核验','否'],
        ['table material','未显式覆盖','unknown','桌面','Isaac FixedCuboid默认','World场景','最终回退值未知','否']]
    with (DOC/'physical_parameters.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(['参数','值','单位','对象','来源','设置位置','验证方式','真实校准']);w.writerows(parameters)
    inventory=[]
    for p in sorted(OUT.iterdir()):
        if not p.is_dir():continue
        if not any((p/name).exists() for name in ['provenance.json','result.json','failure.json','gate_result.json']):continue
        result=load(p/'result.json') if (p/'result.json').exists() else load(p/'gate_result.json') if (p/'gate_result.json').exists() else load(p/'failure.json') if (p/'failure.json').exists() else dict(status='incomplete_or_initialization_failure')
        inventory.append(dict(directory=p.name,status=result['status'],full_success=False,raw_output_preserved=True,provenance=str(p/'provenance.json'),video=str(p/'video/episode_0000.mp4') if (p/'video/episode_0000.mp4').exists() else None))
    save('attempt_inventory.json',inventory)
    eligible=[]
    save('training_index.json',eligible)
    lines=['# lab_cuvette_loading V0_ext01 外部资产接入结果','',
    '本轮实际替换器皿及干扰器皿、仪器外壳和两候选内部座的视觉与碰撞。来源架继续为V0参数化代理，未替换；机器人复用旧Franka。没有隐藏旧代理装载座。当前完成坐标标准化及独立加载，物理精度和配对关口未通过，完整任务与standard/random未放行。calibrated=false。','',
    '最关键的问题是：文件器皿约14.85×14.85×67.5mm，两候选部件的部分限制截面约12.6mm；声明的居中直立竖直路径存在实际边界相交。旧15mm来源孔只有约75微米单侧名义余量，实际支撑抖动，烹饪表示误差及源几何桌面越界均超过该尺度。不能归因为单纯控制器问题，也没有为成功缩小源器皿、放大孔或移除墙。','',
    '## 分阶段状态','',table(['项目','状态','限制'],[(x['item'],x['state'],x['limits']) for x in status]),'',
    '## 来源与保护','',f"- 分支：codex/lab-cuvette-external-assets；起始提交44b2cf46a2bb16330be076ee5c528dc2c0054623。实际运行commit、dirty和源码SHA均在每次provenance及source_snapshot中。",f"- 原压缩包SHA256：`{src['archive_sha256']}`，与交接值一致。原包及解压内容只读复制，包内Python脚本仅阅读，未执行。",f"- V0保护复核：{preserve['protected_files']}个文件、{preserve['unique_inodes']}个唯一inode，SHA256全部一致，旧inode和硬链接计数均未改变。",'- 外部TestTube_629.usd含/root绝对OBJ引用，保留来源记录，未作正式入口；没有原始STEP、尺寸图或真实测量。','',table(['文件','字节','SHA256'],[(x['archive_member'],x['size'],x['sha256']) for x in src['files']]),'',
    '## 资产角色对应','',table(['任务角色','V0实现','外部文件或prim','替换状态','依据与待确认'],[(x['role'],x['V0'],x['external_file_prim'],x['replacement'],x['identity_evidence']+'；'+x['unknown']) for x in roles]),'',
    '## 坐标与尺寸','',
    '- 场景及派生USD为米和Z-up，defaultPrim=/Asset。器皿原Y-up做一次+90度X旋转；仪器原Z-up保留/RotatedRoot已有+90度X旋转，只叠加毫米到米及原点平移，不重复旋转。',
    '- 以实际变换后顶点AABB的XY中心和最低顶点定义资产原点，原点不等同质心。源Mesh局部点先乘原完整USD变换M，再按行向量乘转换矩阵T：p_normalized=[p_source_world,1]@T。T保存在conversion.json，逐实例记录避免prototype重复计数。',
    '- 仪器遍历普通Traverse得到0 Mesh，遍历instance proxies得到8 Mesh，包含两个同prototype候选座；本版静态碰撞每个实际实例只计一次。源材质绑定和GeomSubset均记录，外壳视觉保留源材质，器皿透明是本轮派生外观假设，另保留原始材质wrapper及不透明变体。',
    '- 文件几何：器皿源XYZ约14.85×67.5×14.85mm，标准化后14.85×14.85×67.5mm；仪器实际点尺寸约520.5×634.625×435.481mm；候选件各20.4×20.4×29mm。它们不是实测尺寸。V0来源架138×104×22mm、槽15mm/深18mm未替换。',
    '- 仪器安装原点[0.36,0.22,0.74]m、yaw0为场景安装假设。两个候选件中心约[0.2101,0.3676,0.8995]与[0.2101,0.2636,0.8995]m。准确顶点尺寸与规范场景位置见dimensions.csv；每次实际初态另存。',
    '- 新进程5个派生USD全部加载，必要依赖解析，实际视觉顶点最大坐标差约1.8e-16m或0。这只证明变换计算一致，不是源文件/真机精度。器皿和原始OBJ顶点最近距离最大约1.2e-8m，支持来源一致。','',
    f"![候选部件位置]({DOC/'candidate_locations.png'})",f"![源器皿与座截面]({DOC/'source_sections.png'})",'',
    '## 配对可行性和负例','',
    '两座均按原尺寸检查，采样高度步长0.25mm、数值epsilon0.1微米；这是计算设置，不是真实分辨率。取器皿底部位于座顶下10mm、轴向平行且居中的几何探针姿态，两座均有40个采样截面出现实际边界相交，证据点与高度逐条保存。接近座顶28.5mm高度的中央边界间距约12.6mm，相对器皿外宽的名义总冲突约2.25mm。不同高度有开口、孔或实心底，中央最近边界间距不是“全深度有效孔径”，报告不取全局最小值来概括方孔。',
    '这证明声明姿态/配对存在干涉，不证明所有可能方向、倾角或零件身份都不可能。完整路径的入口、有效装载深度、底面、夹爪净空及盖子避障尚需身份与几何确认，不能用局部相交试验声称完整任务已经判分。',
    '负例把实际源器皿底部放在座顶上5mm，对真实网格做相同截面检查，零相交但位于装载区域外，明确返回geometric_inserted=false及full_success=false；不把“没碰撞”当成功。完整装载独立判分尚未建立/冻结，旧18mm等门槛没有沿用。',
    '新器皿＋V0 15mm装载座仅列为混合配置的名义余量分析，未使用它替代外部仪器目标，也没有隐藏代理孔用于判分。来源架的旧±0.25mm槽内扰动超过75微米余量；新配置预留±0.025mm但尚未运行random，不能据此认为采样合法。','',f"![配对实际网格叠加]({DOC/'pairing_sections.png'})",'',
    '## 物理模型和有效性限制','',
    '器皿源网格合并重复顶点后884顶点、闭合、面方向一致，材料实体体积约5.0815e-6m³。质量仍假设20g，均匀密度约3935.84kg/m³，不是玻璃实测密度。按闭合空腔壁体积分，质心约[0.000000897,0.000000904,0.029027632]m；主惯量约[1.14570e-6,9.52417e-6,9.52417e-6]kg·m²，主轴与完整张量单独保存。没有复制V0实心外盒惯量。实际PhysX和tensor读回与这些写入值相符，但不构成真实校准。',
    '仪器八个原始实例Mesh逐三角形复制为静态碰撞，保留原开口；部分源仪器/候选件网格不闭合，未使用不可靠的封闭体contains给它们做体积和质量积分。动态器皿最终将源三角形按64径向扇区和3个源倒圆过渡高度带切分，加凸底，共193个凸体。壁起始面排除0.1微米共面底板，避免凸化将内腔填平，未改变源视觉和实物尺寸。',
    f"初次自动凸分解23凸体的采样外扩约1.550mm；最终193分块的烹饪表示抽样仍有约{cook['sampled_overreach_max_m']*1000:.3f}mm外扩、{cook['sampled_missing_count']}个漏覆盖样本。PhysX烹饪表示API已实际返回顶点/索引；这不是完整场景actor shape dump，静态Mesh精度也未做全量读回。12000点的抽样误差仅是最大偏差的下界，不是Hausdorff上界。不能把它与75微米余量比较后宣称可用。",
    '本地schema的凸体minThickness默认1mm；本轮显式写0以排查额外加厚，但表示误差没有因此消失，根因未完全确定。未把contact offset当几何膨胀或精度；没有改变rest offset改善孔径。GPU兼容凸体烹饪警告有CPU回退，本轮使用CPU PhysX；不声称支持粒子/软体。',
    '独立源网格顶点与实际姿态审计发现桌面越界约0.28mm。落稳/侧壁结果中的SUBTASK_SUCCESS只是接触、速度和原点高度屏查，不是无穿透或几何精度通过。机器人继承的有效惯量确实与旧USD数值一致；原单位标记与场景不同，其真实/有效尺度依据仍未确认，未随意重建机器人动力学，相关物理真实性结论受限。',
    '完整参数清单见physical_parameters.csv。恢复0、摩擦0.6/0.5、指1.0/0.8、组合average、新体contact/rest=50微米/0、旧架继承100微米/0、CCD和240/60Hz等均区分作者值、配置值和读回项；无法读回的接触偏移/回退材质明确为未知。','',f"![源轮廓与烹饪凸体截面]({DOC/'cooked_sections.png'})",'',
    '## 实际运行与数据','',
    table(['目录','实际结果','仿真秒','run函数墙钟秒','解释'],[(name,(r:=load(OUT/name/'result.json'))['status'],r['simulation_seconds'],round(r['wall_seconds'],2),desc) for name,desc in [('drop_final01','从台面上25mm自由落下并接触落稳；几何精度未通过'),('side_final01','0.4m/s初始化侧向速度；真实侧壁接触峰值约0.357N'),('rack01','新器皿＋旧架持续抖动'),('grasp_final01','支撑不合法，2秒处停止进入抓取'),('grasp_table02','保持子阶段约8.625秒；释放后约90度倾倒，整体失败')]]),'',
    '上述墙钟为run函数内设置/测量/执行时长，不含SimulationApp完整启动关闭，不能当独占GPU性能基准。开始前已有PID491444占显存，未停止。开发grasp01与grasp_table01曾短暂重叠启动/关闭，全部保留且排除性能比较；后续入口增加flock顺序化。没有开展成功率或性能配置比较。',
    '实际动作、双RGB、9维机器人状态、对象位姿、接触点/力/分离量、阶段和时间已保存。H5延续8维动作和学习观测语义，60Hz记录、240Hz逐物理状态，obs/action/next时序审计通过。新的progress只有actual_held列；重叠占位值不可作为测量。所有diagnostic都full_success=false、success=false，不进入完整任务训练索引；未开展ACT/DP训练或完整成功batch验证。',
    '开发失败保留：USD离线schema依赖修复、结果JSON序列化失败、调试截图数值类型修复、早期额外字段长度错误、传感器预热导致初始下落在录制前完成，以及初态窗口包含落稳瞬态。后续修复均有独立新输出；原始文件不覆写。metadata_errata.json纠正旧字段零碰撞误差含义及其他元数据问题。','',
    f"- {link('自由下落完整诊断录像',OUT/'drop_final01/video/episode_0000.mp4')}",f"- {link('侧壁接触完整诊断录像',OUT/'side_final01/video/episode_0000.mp4')}",f"- {link('旧架支撑失效与抓取停止录像',OUT/'grasp_final01/video/episode_0000.mp4')}",f"- {link('桌面夹持保持及释放倾倒录像',OUT/'grasp_table02/video/episode_0000.mp4')}",f"![夹持保持与失败释放实际轨迹]({DOC/'grasp_table02_trace.png'})",'',
    '## 复现入口与记录','',f"准确命令见{link('运行README',ROOT/'demos/lab_cuvette_external/README.md')}。新版本独立run.sh已实际运行scene、physics/drop/side/rack/grasp/grasp_table及task/standard/random关口；完整任务关口只记录blocked，不是10/20次完整测试。新配置路径为config/lab_cuvette_loading/V0_ext01.yaml。build.py在已有派生目录时拒绝覆盖，正常查看直接加载交付资产。",'',
    '## 最少补充信息','',
    '优先补充候选座身份与装载方向、器皿和仪器是否配套，以及一组器皿外宽/座限制净宽的测量。其他信息可分步提供，不要求立即完整标定。',
    table(['缺少信息','影响步骤','当前假设或阻塞','最小补充方式'],[(q['missing'],q['affects'],q['current'],q['minimum']) for q in questions]),'',
    '## 证据索引','',
    '\n'.join('- '+link(p.name,p) for p in [DOC/'source_manifest.json',DOC/'asset_roles.json',DOC/'conversion.json',DOC/'dimensions.csv',DOC/'independent_load_validation.json',DOC/'feasibility.json',DOC/'vessel_mass_properties.json',DOC/'physical_parameters.csv',DOC/'diagnostic_audit.json',DOC/'attempt_inventory.json',DOC/'metadata_errata.json',DOC/'baseline_before.json',DOC/'baseline_after.json',DOC/'archive_integrity_after.json',DOC/'environment.json',DOC/'stage_status.json',DOC/'questions.json']),''
    ]
    (DOC/'report.md').write_text('\n'.join(lines))
    print('DELIVERY_REPORT',DOC/'report.md')

if __name__=='__main__':main()
