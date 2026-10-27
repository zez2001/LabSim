# 发布版生命周期与数据闭合

本页描述 `Project_release_v1` 的独立实现。物理场景、执行器、GenericContactHold、跟踪补偿和评分数字继续复用 Project_v1_1；旧代码和旧结果不改写。CPU 契约不能代替 Isaac 同进程物理运行。实际物理结果见本轮验收记录。

## 已确认并修正的工程问题

旧 v1.1 collector 调用父类后已经将 H5 标为 complete、写入结果和索引，再二次打开 H5 附加 qualification。后半段异常可能留下资格未完成的已完成记录；重复调用 finish 会报错。旧环境清理也假定 finalize 已到达视频关闭尾部，提前的写入或渲染异常可能跳过它。

新版本只通过独立 task、collector 和 facade 启用修正：

- streaming 数据集、相机规格、8D reader 映射和 9D 实际命令不变。
- H5 写入期 `complete=false`、`publication_state=recording/finalizing`；qualification 一次写入。
- collector 先关闭自身视频与 H5，保留 `publication_state=prepared/complete=false`，不发布索引。task 完成相机元数据、native 终帧、三路视频释放、recorder/gzip footer、日志 receipt 和最终结果后，才调用唯一的 `commit_publication` 发布完成标记、H5 资格和正式 JSONL 索引。
- 每个结果、完成标记、索引和 H5 均携带相同 `finalization_id`。普通 reader 对声明了 publication_state 的新文件只接受 complete 状态；历史文件筛选不变。
- finish 完成后用相同结果再次调用返回原标签，不写重复索引；试图重标注报错。
- collector 准备后任意 task 尾部失败，同样走 `abort_publication`：取消本集完成标记和索引、H5 标记 failed/incomplete、结果标记 failed；保留原轨迹便于诊断，旧集 H5 不变。磁盘彻底不可写时不能保证还能写出诊断文件，不宣称能从中断处恢复。
- close 而未 finish 的记录仍 incomplete，不进入训练索引。
- cleanup 无论某一 owner 是否关闭失败，都继续释放其他视频、collector、物理 recorder、相机和 world；异常另存 cleanup_errors。
- reset 建立新 UUID、重建 scorer/contact hold/tracking，对旧 observation/action 拒绝执行。标准配置禁止来源槽位覆盖。

## 同进程三集验收入口

以下命令是本轮原生验收入口；完整实际结果与运行 SHA 由同名输出目录和发布清单记录，不能将本页命令本身作为已完成证据。

```bash
LABSIM_ASSET_ROOT=/path/to/pinned-asset-cache \
  /path/to/isaac-python -m demos.lab_cuvette_project_release_v1.run \
  --config config/lab_cuvette_loading/Project_release_v1/standard.yaml \
  --headless --sequence teacher early_finish teacher \
  --output outputs/lab_cuvette_loading/Project_release_v1/same_process_01
```

三个 episode 使用同一个 Isaac 进程及相同 seed、固定标准场景。第 2 集真实执行预设 3 秒零增量动作后主动 finish，不是模型推理，也不是完整任务成功；前后两集调用原教师控制器。可显式选择 `--sequence no_progress` 和 `--no-progress-after-s 5`，验证预先声明的交互时长上限。

`--record-mode collect` 与正式 CLI 相同：完整物理/接触日志 lossless gzip level1，取消 collector 的第四路重复视频；H5 双相机 60 Hz 和 native 侧视、腕视、双视角 30 Hz 保持。`eval` 当前采用相同持久化规格；不会把它宣传成无图像的轻量评测。`diagnostic` 保留原 plain JSONL 和额外 collector 视频。执行调试 JSONL 仍保留，线上物理/评分 240 Hz、策略观察及数据 60 Hz 均不变。压缩收益和墙钟影响必须依据实际对比结果。

另外可顺序运行 `--sequence early_finish no_progress unreachable service_timeout user_interrupt`。unreachable 对真实超关节上限目标检查零步预规划拒绝；timeout/interruption 是有明确标记的受控异常注入，不冒充真实服务断线或用户实际按下中止。各案例先真实推进物理和记录，再走对应终止路径；`controlled_termination.json` 保存完整回执及重复 finish 不改结果的检查。

每集输出 `reset_audit.json`、`facade_reset_audit.json`、实际 `initial_debug.json`、相机元数据、数据、录像、评分和完成标记。运行级输出 summary、reset_checks、resource_samples 和 run_manifest；资源为采样值，不能冒充连续精确峰值。

collect/eval 关闭后的 `recording_closed_receipt.json` 提供每条流的行数、原 UTF-8 字节数与 SHA256、存储字节数和 close 耗时，包含 reset 的早期下落行。进程退出后可用 `python -m demos.lab_cuvette_project_release_v1.recording RUN/episode_0000` 全量解压核对 SHA、行数与 gzip EOF/CRC；此命令检查源 PID 已退出。公共辅助函数 `iter_jsonl` 同时支持 plain JSONL 与 gzip，正常 H5 reader 不受影响。

## 多集索引与读取

进程实际退出后执行；构建器检查 run_manifest 的源 PID 已不存在，拒绝读取活动 Isaac 进程中的轨迹。

```bash
python -m demos.lab_cuvette_project_release_v1.dataset_index \
  outputs/lab_cuvette_loading/Project_release_v1/same_process_01 \
  --output outputs/lab_cuvette_loading/Project_release_v1/same_process_01/index/episode_data.hdf5
```

默认索引使用**相对 HDF5 链接**，不复制多 GB 图像；它不是单文件自包含数据。移动时必须连同报告声明的三个来源 H5 一起移动，保持相对目录。可用 `--mode copy` 创建真正自包含索引，会额外占用接近来源 H5 总和的空间。两种方式均由正常 ACT/DP reader 读取，原成功标签不改变。

```bash
python scripts/read_lab_cuvette_env_v1_data.py \
  outputs/lab_cuvette_loading/Project_release_v1/same_process_01/index/episode_data.hdf5 \
  --sample-filter all_valid --policy-type act
```

将 `all_valid` 分别换为 `success` 和 `failure`；DP 使用 `--policy-type dp --n-obs-steps 3`。正常 outcome 为 teacher 成功、受控任务未完成、teacher 成功时，预期筛选集数分别为 2、1、3，最终必须以实际运行标签为准。

## CPU 验证边界

`tests/test_lab_cuvette_project_release_lifecycle.py` 包含幂等闭合、重标注拒绝、未完成排除、部分 stream 写入排除、索引/完成标记/H5 最终提交受控故障、旧集字节保护、多集 ACT/DP 读取、相对索引移动、reset receipt 清理、槽位覆盖拒绝与资源关闭异常继续清理。故障均为可控 CPU 注入，不是磁盘损坏、硬杀 Isaac 或真实模型断线证据。

底层现场记录仍保留原生速度与位姿差分差异、effective cooked collision 未完整验证等历史告警。新事务与索引不改变任务评分，也不将真实标定设为完成。
