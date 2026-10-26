# 新侧视的真实模型图像质量比较

同一份明确标记的离线重建状态，分别向Cubence gpt-6-astra发送512×384 low与640×480 high双图，各一次，无动作。两次输入原JPEG、公开机器人状态、实际重建相机标定、响应与费用保留。合计2请求、估算0.08853美元，计入原共享账本。此检查不运行新物理任务，不按物体真值裁剪，也不提供真值坐标。

640输出更明确描述直立开口器皿、双指与机壳前缘的重叠；512输出对器皿身份更保留。两种都明确此视角下目标座、深度和支撑不可确认。只有单帧各一次，不能给出识别准确率或延迟统计；640实际响应11.73秒、51219.46秒不可外推快慢。

下一次调试显式使用独立cubence_gpt6_context4_640high.json，保留原模型、工具限制、2个完整历史回合、超时及共享30美元/1500次预算；默认512配置与旧结果不变。选择更高输入细节是工程判断，仍需核对新轨迹实际双图与独立成败。

已保存snapshot可用现有只读图像比较入口复核，使用新的输出目录；该命令会再次消耗共享预算，凭据从既有环境变量读取：

```bash
python -m demos.lab_cuvette_project_v1_1.camera_audit \
  --snapshot docs/lab_cuvette_loading/Project_v1_1/camera/api_side_v3_comparison_01/snapshot \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high.json \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/camera_compare_NEW \
  --allow-network
```
