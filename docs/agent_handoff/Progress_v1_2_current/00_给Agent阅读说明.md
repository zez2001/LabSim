# LabSim Progress v1.2 结果阅读包

先读 RESULTS.md，再看 cases/teacher_online/progress_report.html。包中只有本轮修订、真实案例和验证证据，不包含 H5、模型资产、Isaac 环境或训练框架。

- `cases/teacher_online`：本轮新运行的普通 Teacher 完整标准任务，全部控制步 Progress、事件、summary 和真实双视角连续录像。
- `cases/pi05_incomplete`：同一真实历史 π0.5 记录的新分析，展示来源架上原始投影与有效插入进度的区别。
- `cases/held_incomplete`：历史真实抓持、离架及持物搬运后未完成案例；保留原 Project_v1_1 版本与策略身份，作为独立诊断参考。
- `guide`：当前使用入口、字段迁移、schema 和参数。
- `validation`：独立漂移复算、事件重放、在线离线逐控制步一致性、原 scorer/reader、文件保护与可视化验证。
- `publication.json` 与 `protection_final.json`：最终发布提交、CI、运行/分析版本和历史文件保护凭据。

每条案例可直接打开 HTML。通过 HTTP 阅读时服务器须支持 Range；否则播放器可能无法拖动。光标读数分别标明请求仿真时刻和实际采样时刻。所有录像都是原始实际记录的 H264 显示副本，未拼接或生成帧。每个 `portable_media_receipt.json` 保存原视频与副本的帧数、时长及 SHA256。

逐步文件沿用 `progress_v1.jsonl.gz` 名称，schema 显式为 v1.2。轻量副本使用更高 gzip 压缩率，解压后的全部 JSONL 字节与原输出一致；压缩前后哈希分别记录。不要仅按文件名判断语义，也不要将旧 `insert.continuous` 当作有效任务进度；使用 `valid_insertion_progress` 或 `effective_continuous`。

源码仓库：https://github.com/zez2001/LabSim
开发分支：{{BRANCH}}
发布提交：{{SOURCE_COMMIT}}
打包时间：{{GENERATED_AT}}

原资产、场景、物理参数、控制器、reward、独立 scorer、资格与历史记录受保护。新接口是因果注释，输入网格几何检查不等于完整 cooked 碰撞表面测量或真实标定。包内最终 CI/保护凭据和文件清单是交接版本的核对入口。
