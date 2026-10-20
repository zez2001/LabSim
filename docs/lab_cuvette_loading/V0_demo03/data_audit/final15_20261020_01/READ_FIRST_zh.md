# 正式 15 条轨迹：只读验收完成

固定 5 条及显式选择的随机 10 条均通过独立物理判分、数据接口、记录身份、装配随机化及动作时序检查；225/225 项独立任务检查成立。合计 **55,609 个控制转换、222,451 条物理状态**。随机槽位 A1、A2、B1、B2、C1 各两条；撤离后实际稳定窗口为 3.1–3.1167 秒。该小样本不是全部槽位、任意布局或真实任务的成功概率。

原随机目录只选择已完成的 seed8000–8007；seed8008/8009 使用独立恢复目录的完整记录。原 seed8008 的工具中断记录完整保留并排除，未打开其 H5。它没有独立末态判分，`physical_failure_verdict=null`：既不能当物理任务失败，也不能声称已经排除物理故障。

现有 `MinimalPickDataset` 已实际从新索引读出 batch：两个 RGB 各 `[1,3,256,256]`、agent `[1,8]`、action `[1,16,8]`、is_pad `[1,16]`，动作有限。额外保存 `qualified_index/read_batch_sample.npz`，经原动作/状态逐元素及 RGB 反量化像素核验，`allow_pickle=False` 重载通过。没有训练、策略推理或优化器操作。

主要入口：

- `compact_summary.json`：简明计数、槽位覆盖、窗口及 loader 结果。
- `acceptance.json`：最终验收、15 条源 H5 SHA256 及最终复核未变标志。
- `all15_source_hashes.csv`：逐条帧数、阶段身份、稳定窗口、原始路径及哈希。
- `formal_audit/audit.json`、`formal_audit/episodes.csv`：逐条完整接口/装配/动作/最终标签检查。
- `excluded_interruption.json`：原 seed8008 中断排除依据。
- `qualified_index/result.json`：过滤结果及现有 loader 实读结果。
- `qualified_index/episode_data.hdf5`：指向原 H5 的小型外链索引；**不包含完整 RGB/轨迹，离开原数据路径不能直接使用**。
- `qualified_index/read_batch_sample.npz` 及验证 JSON：一个真实便携 batch，**不是完整 episode**。

每条完成 H5 的 SHA256 在验收前、接口检查后及索引验收后均核对未变。原始物理、历史评分、保守 `result.json` 字段及末条 `progress.stable=false` 没有回写。最终稳定资格来自实际撤离后的物理窗口；最终成功/资格以独立 score、adjudication 及完成 H5 属性为准。

全部 `native_pair_success=false`、`real_calibrated=false`，不将适配演示纳入原 CAD 配套成功率。8 维动作包含七臂绝对目标及左指位置目标，右指下发命令经核对对称；实际观测第八维是左指实测位置。阶段 effort cap 单独记录在物理辅助通道，**未验证仅重放 8 维动作即可完整复现本轮卸载控制**，参见上级 `action_scope.md`。

要重新验收，请在工程根目录使用 `bash .../reproduce.sh 新输出目录`。新输出目录必须不存在；工具只读，不启动 Isaac Sim。
