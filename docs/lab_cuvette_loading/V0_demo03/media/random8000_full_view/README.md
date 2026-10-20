# V0_demo03 单次运行阅读媒体

结果：**WORKFLOW_SUCCESS**；原始状态 `WORKFLOW_SUCCESS`。仿真结束于 61.783333 s。完整主录像为 `main_h264.mp4`，它来自同一次运行全部原视频帧，没有拼接其他尝试。

各阶段片段按保存的events边界提取；未执行阶段在provenance中为unavailable，不会生成虚构片段。末段慢放仅重复播放原帧，没有增加仿真状态。固定近景相机可能不拍到来源抓取或手臂碰撞，应结合全景。

原episode：`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03/random10_20261020_01/seed_8000/trial_00`。逐文件SHA256、实际帧区间、结果标签及命令见 `provenance.json`。原CAD配套和真实标定结论未被媒体制作改变。


## seed8000 全架视角核查

本文件夹来自一次连续的 seed8000 成功运行，不含其他尝试的仿真画面。主录像保留全部 1854 帧，1920×1080、30 fps；仿真时长 61.783333 s，视频时长 61.800000 s。白色 6×6 架体及最近角完整入镜，未补画。RESET 首帧的机器人上部超出上沿，已在 QA 中保留此限制；来源及腔口均可见。ALIGN 之后主片原本就包含同次运行的同步腔内近景，近景不是另一次尝试。

来源片段 `source_extraction.mp4` 从 RESET 0 s 开始，到 TRANSPORT 20.5 s；`grasp_and_extraction.mp4` 单列夹持与拔出。`insertion_handoff_closeup.mp4` 与 `open_retreat_stability_closeup.mp4` 可看支撑交接、松爪、撤离和稳定。判分的撤离后稳定窗口为 58.683333–61.783333 s，共 3.1 s；实际撤离净空约 111.885 mm。15 项独立检查全通过，数据资格通过。

报告建议使用 `reference_scene_correspondence_vertical.png`（1200×1550）和 `reference_internal_A_correspondence_vertical.png`（1200×1620），标注字号 28 px、标题 31 px、脚注 27 px；另保留屏幕横排版本。A1/F6 是工程槽位 ID，图像中的角色对应不构成真实印刷编号或尺寸标定。原 CAD 配套仍为 false，真实标定仍未完成。

静态对照的输入、操作、坐标与 SHA256 见 `comparison_provenance.json`；抽帧 QA 和稳定窗口核对见 `media_visual_QA.json`。旧 dev_03 成功媒体未覆盖且哈希复核通过。
