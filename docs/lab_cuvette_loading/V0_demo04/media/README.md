# V0_demo04 实际运行录像

## diagnostic_01 搬运阶段失败

`failure_transport_main.mp4` 与 `failure_transport_closeup.mp4` 来自同一次实际连续运行 `diagnostic_01/run/trial_00`，仅转换为H.264/yuv420p以便浏览器和文档阅读器播放，没有拼接其他尝试。主录像1920×1080、30fps、29.534秒；近景为该次运行另一视角。实际终止原因为 **GRASP_SLIP_DURING_TRANSPORT**，仿真29.5秒。

已执行自然支撑、接近、双指抓取、拔出及部分搬运；尚未完成对准、插入、支撑交接、松爪、撤离或撤离后稳定。该录像是失败诊断，不是完整装载成功录像。原座几何门控未通过，原尺寸配套未执行，原生配套成功为false。

- `failure_transport_last9s.mp4`：原录像20.5秒至结束，保留原始时间和阶段叠字，不是另一运行。
- `failure_transport_t29.png`：原录像29秒帧，实际处于TRANSPORT。
- `failure_transport_result.json`、`failure_transport_independent_score.json`：对应原始状态及独立判分。
- `manifest.json`：源文件哈希、转码文件哈希、尺寸、帧率、时长与完整解码检查。

原视频写入为30fps，每两个60Hz控制周期取一帧，因此视频时间与仿真时间约1:1；剪辑未改变速度。原叠字中的“target base Fz”应读作整个目标座的合力Z分量，并没有单独隔离底面支撑力；这是历史叠字语义问题，不能用该读数证明已经触底。

DOCX引用的是本目录的视频文件，并未把MP4二进制嵌入DOCX。转发阅读包时请保留完整目录，单独转发DOCX不会携带视频。

## diagnostic_02 搬运后持物姿态偏差

`failure_02_held_deviation_last5s.mp4` 为第二次实际连续诊断运行32.5–37.534秒片段，终止状态 **HELD_POSE_DEVIATION_AFTER_TRANSPORT**，仿真37.5秒。片段保留原阶段与时间叠字，未改速、未拼接。器皿未进入原座，未执行松爪、撤离或完整装载。`failure_02_held_deviation_end.png` 为末帧。原结果、独立评分及新清单一同保存；这不是原生装载成功录像。

## diagnostic_03 连续预插入诊断

`preinsert_diagnostic_03_main.mp4` 和 `preinsert_diagnostic_03_closeup.mp4` 是同一次新运行的完整连续记录，76.934秒（实际仿真结束76.9166667秒）。主录像1080p，30fps，H.264；近景640×640。真实执行：RESET → APPROACH_SOURCE → GRASP → EXTRACT → TRANSPORT → ALIGN → GATE_RETRACT → DIAGNOSTIC_HOLD。

该次完成来源架自然支撑、物理抓取拔出、持物搬运、腔内目标上方接近，以及仍持物时上抬10 mm并保持。10项独立诊断检查通过。原座的几何门控仍未通过，状态 **GEOMETRY_BLOCKED_PREINSERT**，**没有执行INSERT、SUPPORT_TRANSFER、OPEN、RETREAT或VERIFY**。GATE_RETRACT是夹着器皿的诊断上抬，不是释放后手爪撤离；DIAGNOSTIC_HOLD不是释放后稳定观察。完整装载、原生配套成功及成功训练资格均为false。

- `preinsert_diagnostic_03_align_upward_hold.mp4`：原640×640近景的65秒至结束片段，保留真实时间叠字。此视角在末段被手爪遮挡，不能从中看清器皿底部和原座的细小间隙。
- **建议同时观看 `preinsert_diagnostic_03_obs256_camera2_65s_end.mp4`**：直接读取同次H5中实际采集的camera_2_rgb，原观测256×256、60Hz，每2帧导出30fps，覆盖观测时间65.0–76.9秒。为便于阅读仅逆时针转90°、最近邻放大2倍并添加说明，保留原始未旋转PNG。它能看到双指、器皿和内部座之间的关系。没有重放仿真、重建或合成画面。256像素不能检验50微米净空。
- `preinsert_diagnostic_03_obs256_camera2_t73.4_raw.png` / `_view.png`：ALIGN阶段实际观测。
- `preinsert_diagnostic_03_obs256_camera2_t76.5_raw.png` / `_view.png`：DIAGNOSTIC_HOLD阶段实际观测。
- `preinsert_diagnostic_03_before_stop.png`、`_held_after_upward_retraction.png`、`_overview_before_stop.png`：从原录像提取的73.4/76.5秒帧，近景遮挡保持原样。
- `preinsert_diagnostic_03_observation_media.json`：H5数据集名、帧索引、观测/后继时间戳、阶段和像素哈希。
- `preinsert_diagnostic_03_manifest.json`：源视频及转码哈希、帧率、时长、完整解码结果及证据范围。

03叠字已经采用“seat total Fz”，表示整座合力，不能当作独立底面支撑力。清晰的静态腔体几何请见邻目录 `../scene_check/final_static_chamber.png`；它是0任务物理步的reset截图，不能替代实际接触录像。
