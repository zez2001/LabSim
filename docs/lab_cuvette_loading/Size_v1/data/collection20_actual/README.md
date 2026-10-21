# 固定场景20条成功：已闭合21集只读快照

本次实际审计合格20条natural完整成功、1条确定性INSERT提前停失败；目标失败20条尚缺19条。
这不是最终40条交付。只读取源码中明确列出的4个自然进程各5集和已闭合1mm受控进程1集，
未扫描episode树，也没有读取当时活动的5mm受控批次。

5个已闭合官方子进程均有真实wait记录，exit0、非中断；21集均complete，归档均成功。
`collection21_audit.json`保存逐进程/逐集源文件、哈希、生产准入、原始标签和读取证据。
读取过程中检查源H5大小与mtime不变；未改源配置、状态或成功标签，未训练或启动GPU。
CPU数值库及Torch线程限制为2。

20条完整成功均实际释放、夹爪撤离和至少3秒稳定，105.816667仿真秒、6348控制步。
最终深度约27.000035mm，最终倾角约0.013453°；3秒观察的位移漂移约0.000239mm、
姿态变化约0.000713°。这些数值来自固定仿真条件，不能解释为真实标定精度。

实际初态位置、四元数、机械臂7关节和双指状态在20条自然成功间与首集完全相同；
来源槽、目标A座、10mm资产、冻结指纹、场景投影、控制/机器人/物理/判分以及相机配置
哈希一致。唯一1mm失败的这些字段也相同。seed0–4为每进程episode记账，场景随机化关闭。
完全重复的初态结果不是广泛布局下的成功概率。

所有20条成功保留`NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT`和
`NATIVE_TARGET_OVERLAP_UNAVAILABLE`告警；本轮没有删除原生速度，静态完整烹饪座碰撞
仍有读回局限。详细初态、深度、力、稳定窗口和告警见`initial_state_and_results.json/.csv`。

1mm失败通过生产`controlled_event_admission`的全部22项检查：实际teacher事件时刻
62.383333秒，H5后继INSERT状态深度1.016965mm，与配置、事件及终止记录吻合。
它为`CONTROLLED_EARLY_STOP`动作偏差失败，没有释放或撤离，post_retreat_window为
unavailable，stable_after_retreat为null；不称为物理卡滞或短预算诊断。
证据见`actual_controlled_event_admission.json`。

本次仅新建轻索引：

`outputs/lab_cuvette_loading/Size_v1/collection_standard/checks/success20/dataset/episode_data.hdf5`

索引15200字节，指向同collection树内的21个原H5。原episode依旧独立；移动索引需保留
整棵collection相对结构。最终默认`collection_standard/dataset/episode_data.hdf5`未创建。
正常ACT、DP对success和failure四种读取均通过RGB/实际动作逐值核对。
成功BC只读20条成功，按完整episode实际划分18train/2val，无交集；同一固定standard场景。
单条失败读取验证为1train/0val，仅供失败分析。ACT/DP动作batch均为[3,16,8]，
DP采用2个观测时刻。详情见`normal_ACT_DP_success_and_failure_read.json`。

本次实际执行的CPU命令（证据与索引拒绝覆盖，重跑须先复制为独立分析目录并更新新索引路径）：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
 ../labutopia-env/bin/python \
 docs/lab_cuvette_loading/Size_v1/data/collection20_actual/audit_readonly.py
```

已存在轻索引的正常读取命令：

```bash
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 outputs/lab_cuvette_loading/Size_v1/collection_standard/checks/success20/dataset \
 --sample-filter success --policy-type act
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \
 outputs/lab_cuvette_loading/Size_v1/collection_standard/checks/success20/dataset \
 --sample-filter failure --policy-type dp --n-obs-steps 2
```
