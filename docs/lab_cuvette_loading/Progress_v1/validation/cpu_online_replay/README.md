# CPU 在线接入回放验证

这里保存的是 **CPU 回放验证，不是本轮新运行的仿真轨迹**。输入来自历史真实成功记录 `outputs/lab_cuvette_loading/Project_release_v1/same_process_collect_01/episode_0000`。回放不调用仿真、控制器或原 scorer，也不产生新的训练或评测索引。

验证程序把原 `physics_records` 全部物理采样逐条送入正常在线接入使用的 `OnlineProgressSession`，按原 H5 的动作与 `(t_obs, t_next]` 区间调用 transition，再通过正式离线入口读取同一轨迹并作精确比较。原数据只读；临时回放目录通过链接引用原 H5 和物理记录。

这项验证覆盖在线适配器与离线适配器的一致性。它不能代替正常 Teacher 入口的新物理回归、渲染与 reader 验证。初态 `t=0` 与首次控制观测 `t=4/240 s` 分别保存。CPU 回放的器皿局部包络取自当前已核查资产 registry；布局由原场景配置计算，随后持久化给离线过程复用。

- `summary.json`：输入身份、版本、原结果摘要、采样/事件数量、开销、全部大文件路径与 SHA256。
- `comparison.json`：全部控制区间的前后因果状态、区间事件、里程碑、attempt 与 resolved 配置的精确比较。
- `replay_driver.py`：本次执行的 CPU 回放程序，从仓库根目录运行。依赖当前 CPU 测试环境；不会启动 Isaac。

完整 sidecar 保留在 `summary.json` 指明的临时目录中，未加入 Git。CPU 开销包含 Python 标注与写入计时；`lifecycle_wall_seconds` 同时包含原 JSON/H5 的回放读取成本，不是新仿真的性能回归结论。
