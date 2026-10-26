# 9e 接触预载与释放连续性静态契约复核

审查固定提交 `9e48016412907385d1a8c9e40860139f3d730764`，对照 `c793a12b8f097eb47a9158a708d896993a05116c`。只用git对象读取源码；没有扫描raw/H5、读取活跃teacher/GPT、运行CPU数值试验、API或GPU，也没有改runtime或报告draft。10份源SHA、必要差异原行号及范围在 `review.json`。

## 预载反馈何时生效

`gripper_hold.py`第123–124、149–175行：必须提供实际effort上限且允许既有正预载目标、没有显式张爪、双侧接触持续确认，并且弱侧读数低于预载目标的90%，才请求额外慢闭。输入仅为仿真时间、logical/ramped/previous总开口、两指位置/接触力和实际effort；不读取物体位姿、teacher阶段、槽/座状态或评分。task第141–145行新增传实际effort，使新分支不再对该信息盲目。

第42–49行目标仍来自既有mass、mu、safety、kp和最大压缩假设。新增反馈每步总开口减量不超过2mm/s×dt，正常60Hz为33.333µm；首次冻结参考起新增预算为0.6mm，失触重接不重置。第168–171行不允许反馈把更小的合法原目标主动张大。这些界限只约束新增反馈目标，不是原闭合ramp/首次冻结候选、实际材料压缩、全部目标差或穿透的全局上界。

## 显式卸载与release slew

第99–117、129–148行的显式logical张宽优先于预载，并清除接触确认/参考。effort低于预载目标时也禁用新反馈；仅降低一个仍高于该目标的cap并不自动成为开爪意图。

只有确实发生过新增预载收紧、随后显式张宽时，release_slew才开启。它用调用者ramped目标的正增量/dt更新速度，从实际previous目标连续张开，且不超过当前ramped值；调度暂停也不能继续追向未下发的80mm逻辑终点。需实际applied与ramped都到逻辑终点才退出。反向闭合退出释放状态，完全相同样本返回缓存。旧effort=None或未发生新增收紧的原释放路径不套此slew。

这里没有额外引入固定的通用开爪速度上限，它跟随调用者的调度增量；也不保证实际关节以同一速度运动。实际承重/松爪效果仍须由物理记录核验。

## 不变的物理与判分

c793与9e的完整standard.yaml字节相同；acceptance、demo_release、physics、robot、vessel、gripper、executor七组值相同。三个独立scorer、父teacher、新teacher v3、robot_tracking以及实际effort setter来源也相同；修改没有提高8N上限、kp、摩擦或放宽成功门槛。源码保护不代表本审查重新验证过全部运行资产或真实接触。

## EXTRACT朝向与仍活跃的反馈层

固定cfg `control.extract_orientation_feedback=false`。父teacher第249–252行明确将此值传给_feedback；第90–97行朝向更新跳过。新teacher只额外抑制GRASP朝向，_enter也不重设朝向，因此名义rotation_command应保持到EXTRACT结束，TRANSPORT第264行才恢复默认orientation反馈。

但EXTRACT同时仍给_feedback传source_initial[:2]：第98–105行的物体真值XY纠偏仍活跃，只是teacher内部的有权限控制，不是GPT公开输入。task第109–122行还会在名义reference之后应用robot_tracking：其position/rotation残差只来自前次实际下发q的FK与当前机器人状态。补偿第98–101行左乘一个有界旋转偏差，所以上游名义四元数固定并不意味着effective IK四元数逐样本完全相同。该层最大rotation bias为2mrad、position bias为1mm，没有读取器皿真值。

不能仅看最终杯转动就断言“EXTRACT teacher姿态反馈导致”。应在已关闭物理审计中分别对齐requested/nominal、effective IK、actual-joint FK、native hand与杯姿态，再考虑接触和驱动响应。本源码审查不预写实际转动的时刻、幅度或物理因果，也不把任何新轨迹标为成功。
