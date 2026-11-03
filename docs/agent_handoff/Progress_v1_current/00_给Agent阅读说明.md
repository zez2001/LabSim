# LabSim Progress v1 本次结果阅读包

本包只包含本轮新增的器皿装载进度诊断及实际验证证据。先读 [RESULTS](RESULTS.md)，再打开 [本轮 Teacher 完整任务](cases/teacher/progress_report.html)和 [π0.5 未完成示例](cases/pi05_incomplete/progress_report.html)。两个页面带独立侧视、腕视和时间关联，可直接本地打开。

- 交付分支：`{{BRANCH}}`。
- 最终发布提交：`{{SOURCE_COMMIT}}`。
- 生成时间：`{{GENERATED_AT}}`。
- 工程与代码：{{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}}。
- 新物理回归运行提交：`913af8a5989dd328d22752a4bba6431339094306`。

`cases/teacher` 是本轮正常 Teacher 任务开启在线 Progress 后的同一条完整记录；包内逐步 sidecar 使用经精确比较一致的离线副本，原在线目录及原文件哈希见 validation。`cases/pi05_incomplete` 复用既有真实策略终止记录，本轮没有新增付费模型调用。

每个 case 含完整控制步 Progress、稀疏事件、summary、resolved 参数及可视化。视频为原连续录像的 H264 显示副本，保留帧数、帧率和时长；`portable_media_receipt.json` 给出原录像与副本哈希及转换命令。页面在 HTTP 服务中拖动视频需要服务器支持 Range；普通 http.server 不保证可拖动。

[字段映射](guide/field_mapping.md)、[阶段判据](guide/stage_criteria.md)和 [schema](guide/schema.json)解释坐标、单位、证据范围及未知值。`validation` 分开保存 CPU fixture、真实旧轨迹回放、新 GPU 回归、正式 reader、在线／离线一致性和保护检查。首次中断的回归保留为 interruption，不计成功。

原 H5、大型物理／接触日志、资产及运行环境保留在工程端，未放进本包。原最终成功与数据资格由原 scorer/collector 决定；Progress 不修改 reward、训练资格或历史标签。新旧记录的精确位置与 SHA 可在验证文件中定位。

传输后运行 `sha256sum --check SHA256SUMS.txt`。完整源码、运行环境和资产安装步骤通过固定提交的工程入口获取。
