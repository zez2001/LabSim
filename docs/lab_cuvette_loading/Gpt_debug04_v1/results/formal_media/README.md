# 正式单集视频、真实帧与图表

完整媒体目录在原工程 `outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103/media/formal_debug04_01/`。阅读包中对应 `cases/formal_debug04_01/`：打开 `progress/progress_report.html` 查看完整侧视/腕视与 Progress；`formal_debug04_01_dual.mp4` 为完整双视图 H264 显示副本。

显示副本保留原 3031 帧、30 fps、1280×480、101.033333 秒，不裁切、不插帧、不拼接，原视频不变。三路显示视频全部完整解码通过。

`frames/` 的三张图均直接从原 dual 视频按真实帧索引抽取：首次抓持、首次持物横向搬运 50 mm、原终态。逐帧仿真时间、帧索引、源与目标 SHA256 在 `media_receipt.json`。这些图不是新渲染的场景示意图。

`figures/` 包含首次阶段确认时间、有效 Progress 与固定参考漂移，以及适用目标误差三图。未到达的阶段没有零秒时间；目标操作区未到达，目标误差图明确显示 N/A。曲线来自实际控制端点，物理 240 Hz 的区间极值另见量化表。

完整 Progress HTML 只重新绑定便携媒体路径。所有其他 16 个顶层数据字段与同一原记录生成的报告逐项一致。数据传输副本使用无损 gzip 重压缩，其解压内容 SHA 在 `portable_media_receipt.json`；原 Progress 文件、summary 和标签没有更改。

六张最终 PNG 已实际打开核查，验证记录在 `../../validation/formal_visualqa.json`。验证范围包括 PNG 视觉核查、完整视频解码、相对链接和 HTML 数据一致性；没有声称另做了浏览器交互播放测试。
