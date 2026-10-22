# Size_v1 原座固定、器皿横向尺寸假设

资产入口为 `assets/lab_cuvette_loading/Size_v1/registry.json`，以 `asset_id`
选择独立USD；原12.5mm文件和原A座不写回。选定初始物理候选
`cuvette_xy_1000`（10.00×10.00×67.5mm，20g假设），目标原A座局部
XY偏移(+0.650,+0.001)mm，杯底候选Z=2mm、插入深度约27mm。

所有候选共用同一规则diag(width/12.5,width/12.5,1)，包括视觉和28块厚壁
碰撞输入。材质、碰撞参数、拓扑、原点及高度不变；不会制作局部避让。
质量保持20g并对实际闭合视觉材料体积分COM/惯量，数值密度相应改变，
不是物理材质或真实质量校准。每个独立USD重载核查，并保留源和产物哈希。

离线生成（无需Isaac进程或GPU；新目录必须不存在）：

```bash
bash demos/lab_cuvette_external/usd_python.sh \
  -m demos.lab_cuvette_size_v1.build_assets --widths-mm 12.5 11.0 10.5 10.0 9.5 \
  --directory assets/lab_cuvette_loading/Size_v1_REPRO_NEW
```

完整家族扫描会调用build，更新其工作副本的Size_v1注册表及派生元数据，
不能在正式冻结采集的工作区运行。以下在同级新worktree复现，保留所有评估尺寸；
worktree和输出目录须不存在，既有USD运行环境仍从同级labutopia-env复用：

```bash
git worktree add --detach ../LabSim_Size_v1_GEOMETRY_REPRO_NEW HEAD
cd ../LabSim_Size_v1_GEOMETRY_REPRO_NEW
bash demos/lab_cuvette_external/usd_python.sh \
  -m demos.lab_cuvette_size_v1.scan_family \
  --config config/lab_cuvette_loading/Size_v1/standard.yaml \
  --output outputs/lab_cuvette_loading/Size_v1/new_geometry_scan \
  --geometry-site /home/wujing/Desktop/vla/physicalrsi-runtime/sim-env/lib/python3.11/site-packages
```

当前35个已保存资产覆盖9.50–12.50mm。入口必要截面检查的四个直立方位
均遍历全部有界XY域，观察到11.00mm仍有正间隙域、11.02mm起无域。
保守全深竖直扫掠正证书最大已观察尺寸10.70mm；10.72–11.00mm属于入口
可行但保守全深未认证，不写成全局不可通过。10.00mm固定偏移的侧向输入
表面保守余量约0.350mm，静态采样支撑凸包包含按真实材料体积分的COM。

正几何证书不是物理接触、释放稳定或完整任务成功；离线筛选本身不读取PhysX
烹饪形状，也不证明任意倾斜6DoF路线。运行时probe通过官方烹饪请求取得28块
凸体表示并做双向三角表面抽样，未读取已附着PxShape指针；约14μm观察差
不是严格全局误差界，静态原座完整烹饪表示仍未知。
几何证据见
`docs/lab_cuvette_loading/Size_v1/geometry/family_20261021_02/`。

完整任务、固定验证和数据采集从原工程根目录执行。正式冻结配置只接受10mm
资产，直接对它增加`--asset-id cuvette_xy_1050`会被冻结守卫拒绝。其他注册尺寸
必须使用独立、未冻结的探索配置和新输出目录，不继承正式任务资格。

已保存的未冻结探索配置可通过同一入口替换asset_id，例如：

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher \
  --config config/lab_cuvette_loading/Size_v1/variant_evaluation_1030.yaml \
  --asset-id cuvette_xy_1050 \
  --output outputs/lab_cuvette_loading/Size_v1/NEW_VARIANT_1050 --headless
```

该入口同步解析选定资产的视觉、碰撞、宽度和质量属性，保持原座与当前目标轴。
每个尺寸仍需自己的几何和物理判分；此示例不表示10.50mm成功，也不计正式配额。

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher \
  --config config/lab_cuvette_loading/Size_v1/standard.yaml \
  --output outputs/lab_cuvette_loading/Size_v1/NEW_SINGLE_RUN

../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \
  --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \
  --phase success --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION \
  --allow-after-verified-five --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \
  --phase controlled_failure --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION \
  --allow-after-verified-five --headless
```

新collection先通过真实5/5完整任务；成功和受控失败随后可交错采集，优先自然失败。
失败不足时仅改变INSERT动作停止深度1/5/10/18mm，不改变场景。每进程至多5集、
单GPU顺序运行。驱动阶段退出2可表示配额未满，不能与仿真子进程非零退出混淆。
所有仿真进程闭合后才进行目录审计；不要在活动H5写入时扫描。

以下为本次正式collection的最终审计命令，索引与审计输出必须尚不存在。
若复现到NEW_COLLECTION，替换以下两个collection路径，训练配置也应显式指向新索引。

```bash
../labutopia-env/bin/python scripts/validate_lab_cuvette_size_v1_data.py \
  outputs/lab_cuvette_loading/Size_v1/collection_standard \
  --config config/lab_cuvette_loading/Size_v1/standard.yaml \
  --frozen-scene config/lab_cuvette_loading/Size_v1/frozen_scene.json \
  --admission-scope official_collection \
  --index outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset/episode_data.hdf5 \
  --output-json docs/lab_cuvette_loading/Size_v1/data/FINAL_NEW_AUDIT/collection_audit.json
```

验证器同时核对冻结指纹、实际official/closed/exit0进程证据和标签；受控失败还必须
存在实际teacher_events事件，与H5后继时刻、INSERT状态、实际深度及配置一致。
仅声明动作偏差不能进入配额或索引。释放前停止的post_retreat_window为unavailable、
stable_after_retreat为null。原始标签不改写，preview、短预算、初始化/服务失败、
中断进程单列。最终审计同时通过正常ACT/DP读取成功/失败各一个batch，并记录互斥
完整episode的train/val ID；二者均为相同standard场景，训练本身不执行。

正常目录读取固定追加`episode_data.hdf5`；不能改名为index.hdf5后仍传目录。
轻索引采用collection树内相对ExternalLink，移动时需移动整个collection树；
原始episode H5本身没有绝对外链。独立便携成功样例已另行导出，约1.96GB，
其读取与无损归档证据位于`docs/lab_cuvette_loading/Size_v1/data/standard5_actual/`，
不复制到精简阅读包。

```bash
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
  outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset \
  --sample-filter success --policy-type act
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
  outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset \
  --sample-filter failure --policy-type dp --n-obs-steps 2
```

collect/train/训练自动验证强制standard并禁用场景随机化；训练RNG seed单独配置。
ACT/DP任务配置为`lab_cuvette_size_v1_act`和`lab_cuvette_size_v1_dp`，默认只读取
合格成功做BC，失败分自然与确定性动作偏差组。本轮不运行训练、不要求random10。

以后明确启动训练时，可复用正常ACT/DP入口及以下精确override（本轮仅CPU检查
Hydra配置合成，没有执行这些训练命令）。ACT必须覆盖`policy.camera_names`；仅替换
task会继承旧相机名，与本任务观测键不一致。DP从`shape_meta`和obs_encoder自动取得
两路相机，不额外注入不支持的camera_names字段。下列输出目录须不存在：

```bash
../labutopia-env/bin/python train.py --config-name=train_lab_cuvette_loading_act \
  task=lab_cuvette_size_v1_act \
  'policy.camera_names=[side_camera_rgb,wrist_camera_rgb]' \
  hydra.run.dir=outputs/lab_cuvette_loading/Size_v1/FUTURE_TRAIN_ACT_NEW
../labutopia-env/bin/python train.py --config-name=train_lab_cuvette_loading_dp \
  task=lab_cuvette_size_v1_dp \
  hydra.run.dir=outputs/lab_cuvette_loading/Size_v1/FUTURE_TRAIN_DP_NEW
```

只检查配置时，在任一上述命令末尾加`--cfg job --resolve`，Hydra只输出配置并退出，
不会创建workspace、读取H5、启动优化或仿真。CPU合成证据见
`docs/lab_cuvette_loading/Size_v1/runtime/future_training_hydra_compose_cpu_check.json`。
两入口仍只用冻结standard、success过滤和whole-episode划分，自动验证使用同一固定
场景数据；它是离线验证损失，不是本轮已经执行过policy物理闭环评估的声明。

精简交接快照包含35个资产的尺寸/内腔/质量惯量/材质/碰撞参数、原座保护证据、
正式相机与初态、实际事件准入及便携样例小清单。最终数量只从显式最终审计取得，
先前开发成功或局部已完成验证不等于20+20。最终报告放在
`docs/lab_cuvette_loading/Size_v1/results_20261021/`，由主任务在全部闭合后生成。
