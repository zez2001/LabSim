# 新正式单集量化证据

本目录只包含本次授权运行 `debug04_01` 的派生汇总和原始小型记录副本。新组计划 10 集，用户本次授权并实际启动 1 集，另 9 集未授权、未启动。历史 debug04、P9 和 π0.5 均不进入该组分母。

先读 `analysis/summary.json`、`analysis/episodes.csv` 和 `quantification/stages.csv`。本集独立任务结果为失败；记录完整、环境有效、可以评估任务结果。最远确认阶段为持物横向搬运 50 mm，未确认到达固定预插入区。适用目标误差、有效插入深度和合法释放后稳定时间为 N/A。

终帧手指已经实际张开，器皿停在入口局部结构上。合法目标支撑、释放和撤离关口没有通过。`../../validation/terminal_contact_observation.json` 区分原末物理行、3 秒 terminal_window 和不可用的 post_retreat_window；不能把最后画面直立或终末静置当作装载成功。

`metrics/costs/debug04_01.json` 绑定新 UUID 的 42 次实际网络请求，估算费用 $3.445010。`wall_seconds` 是有独立计时的 native run phase；完整整进程墙钟时间没有独立计时，`whole_process_wall_seconds` 保持 null。启动、运行和关闭的已测组件合计另列，不充当精确整进程时间。

`input_samples/` 保存首次和最后一次实际请求对应的原 public JSON 和已经编码的两张 JPEG。历史 vendor 没有保存完整对话 HTTP 请求的规范化哈希，汇总没有补造该字段。原 H5、视频及任务标签保持不变。`source_binding.json` 记录本目录及配套图片/验证文件的来源和 SHA256。

复算命令需要原机完整且已关闭的 episode；阅读包只提供小型证据与完整 Progress 展示，不包含大 H5。以下工具不发起模型调用或仿真：

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Gpt_debug04_v1/tools/collect_formal_metrics.py \
  --run-root outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103 \
  --authorization outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103/authorization_02.json \
  --closure outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103/validation/formal_debug04_01_closed.json \
  --output /new/path/metrics
"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.analysis \
  /new/path/metrics/trials.json --output /new/path/analysis
```

所有输出路径必须不存在。正式运行源码冻结为 `801a3f704298faf00cc31b55d572e5e0ff4bb4b6`；后续文档发布提交和原运行提交分别记录。
