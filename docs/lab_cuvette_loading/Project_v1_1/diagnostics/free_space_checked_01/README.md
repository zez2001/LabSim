# free_space_checked_01：闭合记录的独立 CPU 审计

本次三组完整诊断均完成，每组 24 个 signed probe，共 72 个。原进程 exit 0，process_exit.json 记录 session 40474 / PID 4003768，审计时 `/proc/4003768` 已不存在。此审计只读取 JSON/JSONL，未读取 H5、改写标签或压缩原始记录。

原始任务结果均为 `task_success=false / CONTROL_DIAGNOSTIC_COMPLETE / budget`；诊断通过不代表完成器皿装载。`post_retreat_window` 保持 unavailable，稳定结果为 null。

- **pose0_world**：24/24，仿真 62.216667 s；完整回锚最大 17.97 µm / 0.0344 mrad；终点最大误差 11.63 µm；路径最大跟踪误差 0.30461 mm，横向偏离 0.23894 mm。
- **pose1_world**：24/24，仿真 63.933333 s；完整回锚最大 16.33 µm / 0.0156 mrad；终点最大误差 12.12 µm；路径最大跟踪误差 0.30047 mm，横向偏离 0.23601 mm。
- **pose1_tcp**：24/24，仿真 63.966667 s；完整回锚最大 16.70 µm / 0.0156 mrad；终点最大误差 12.87 µm；路径最大跟踪误差 0.30172 mm，横向偏离 0.22445 mm。

## 结果边界与测量问题

每次平移均从实际观测的固定起点执行，并先恢复固定完整 xyz+wxyz。CSV 分别保存目标相对实际起点的误差、相对理想固定 anchor 的误差、实际净位移、路径长度和控制边界误差；不能把名义幅度当成实际位移，也不能用终点误差代替全程误差。

三秒绝对 hold 中，ep0 记录的 TCP 与臂关节 q7 不变，ep1/ep2 的 TCP 最大变化分别为 0.649 / 0.134 µm；三组原生关节速度峰值仍约 0.0245–0.0256 rad/s，明显大于差分速度。两种信号分开保存，未删除或替换。本审计没有确定缓存、休眠或求解器内部机制。记录不变或微小变化不能作为精确物理零运动或真实标定精度的证明。

路径最大值仅覆盖控制边界，不是物理子步的严格上界。本文结论限于本配置下的机器人自由空间重复探针；没有验证器皿接触装载，也不能推导 Isaac Sim 的真实微米精度。

## 文件与复现

- `audit.json`：闭合证据、三组统计、源 SHA256、代码/资产/场景元数据、独立速度与测量限制。
- `probe_results.csv`：72 个实际探针的逐条结果（字段名注明单位）。
- `group_results.csv`：三组的摘要。
- `probe_metrics.png`：实际位移、终点误差、全程误差与完整回锚姿态。
- `actual_probe_paths.png`：各组实际路径叠加；tcp 组投影到固定 anchor 的 TCP 坐标系。
- `hold_velocity_discrepancy.png`：三秒 hold 的原生/差分关节速度与记录的 TCP 漂移。
- `generate_audit.py`：纯 CPU 复现程序；保留原审计，重跑时必须指定新的输出目录。

三集实际 reset 的机器人 q9 与 TCP 记录完全一致，场景 fingerprint 一致。另一个审计流程已实际完成三 H5 全读与回执时间链检查；参见 [独立 H5/归档审计](../free_space_checked_01_closed_read_archive.json)。该验证由另一审计代理完成，本文没有打开 H5。

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Project_v1_1/diagnostics/free_space_checked_01/generate_audit.py \
  --output outputs/lab_cuvette_loading/Project_v1_1/free_space_checked_01_audit_new
```

此前 `free_space_checked_01_preliminary.json` 是父进程尚在运行时的 ep0 快照，原样保留；本目录为完整闭合后的新增分析。
