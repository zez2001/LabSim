# Env_v1 独立判分

实现：`tasks/lab_cuvette_loading_env_v1_scorer.py`，类 `CuvetteLoadingEnvV1Scorer`。

环境每个已完成物理步调用 `update(row)`，收尾调用 `finalize(episode_id, task_type, termination_reason, failure_type)`。行记录必须来自同一物理步结束后的真实状态。教师阶段名称和控制器自报成功均不作物理通过依据。

完整装载判分检查实际双指夹持、源槽清出、持物搬运、目标姿态及深度、按实际接触点分区的底部支撑、双指打开和失去接触、整手几何净空，以及实际撤离后至少3秒的稳定窗口。整个座的合力Z不代替底部承托；未知重叠、支撑或区域量不补零、不当作通过。真实发生的显式张爪和再次夹持构成可追溯的新尝试，先前漂移保留，允许合法恢复。

`preinsert_diagnostic`有独立目标：清槽、搬运、接近保守停止区、真实上抬及持物保持。它不能获得完整loading成功标签，也不进入完整装载成功索引。没有实际撤离时，`post_retreat_window.status=unavailable`且稳定结果为null；中止前窗口另存`terminal_window`。

当前已实际读取demo04第三条18461步历史记录进行只读复核，见 `historical_demo04_diagnostic03_final.json`。这不是本轮新仿真，也未覆盖旧评分。历史轨迹确实取出并搬运、最后1秒持物稳定，但从接触参考开始相对手部累计漂移约3.986mm/3.930°；新有界抓持判据因此给出GRASP_SLIP。分段测量显示静持约52.47µm/0.0597°、提取约9.85µm/0.0107°、搬运约4.000mm/3.9437°，问题主要发生在搬运段。新判据与旧诊断范围分别保留。

上述位移以器皿底部原点为基准，包含倾斜的杠杆效应，不能解释成4mm纯轴向滑移。按配置抓取高度53mm参考点复算，最大位移约0.561mm，沿初始器皿轴向约0.445mm、横向约0.342mm；该点不是实测压力中心，详见`historical_grasp_anchor_kinematics.json`。图`historical_grasp_drift.png`显示约26–28s搬运段姿态和原点漂移突变，同时旧控制器仍给零宽闭合目标。接触力矩的因果解释还需实际接触点/法向/摩擦与控制响应对齐。

历史复核可使用下述脚本；输出必须指定一个不存在的新文件：

```bash
../labutopia-env/bin/python docs/lab_cuvette_loading/Env_v1/scorer/regrade_historical.py \
  --source outputs/lab_cuvette_loading/V0_demo04/diagnostic_03/run/trial_00 \
  --audit <对应原资产的几何审计JSON> --output <新的分析JSON路径>
```

8个判分逻辑测试已在现有Isaac Python通过：

```bash
../labutopia-env/bin/python -m unittest discover -s tests \
  -p test_lab_cuvette_env_v1_scorer.py -v
```

测试中的成功状态序列是明确标注的合成逻辑夹具，只验证没有写死false及正确处理unknown、误导阶段标记、分区支撑、重试和诊断范围。**它们不是成功仿真、策略表现或数据集成功数量。** 本轮真实物理执行由环境运行记录另行验收。
