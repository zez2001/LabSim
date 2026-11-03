# 历史 debug04 完整录像与真实画面

完整便携目录位于工程输出
`outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103/media/historical_debug04/`：

- `historical_debug04_dual.mp4`：完整双视角H264显示副本，1280×480、30 fps、
  3,442帧、114.733333秒；全部原帧顺序与原录制保持一致。
- `progress/progress_report.html`：全部6,882条控制记录与49条完整事件，
  包内相对路径播放原侧／腕H264显示副本；两路各保留全部原帧。
- `media_receipt.json` 与 `progress/portable_media_receipt.json`：原文件和
  显示副本的SHA256、时长、fps、分辨率，以及gzip转移副本解压字节一致证明。

本目录仅保存报告必要的4张真实双视图、3张科学图和小型凭据；不复制大型H5
或原始全视频。来源均为同一历史episode
`28bd2fc2-7bd7-44ee-9fb6-aaff53cbc99d`，没有新的仿真或模型调用。

四张截图是原 `dual_view.mp4` 的直接选帧，未拼接另次尝试或生成运动：

- [首次抓持](frames/historical_debug04_01_first_grasp.png)：请求14.112500秒，
  实际原帧14.116667秒，零起始frame 423。
- [固定预插入区域到达](frames/historical_debug04_02_first_preinsert.png)：
  请求和原帧均66.850000秒，frame 2005；该阶段不等于对准或装载。
- [首次抓持质量告警附近](frames/historical_debug04_03_first_quality_warning.png)：
  控制端点71.900000秒，最近原帧71.883333秒，frame 2156。
- [实际结束状态](frames/historical_debug04_04_terminal.png)：114.716667秒，
  原始最后frame 3441；原任务仍失败，无脱指／撤离／稳定证据。

三张图全部来自真实Progress记录：

- [首次阶段时间](figures/01_historical_first_times.png)：未达阶段不伪造0秒。
- [有效Progress与抓持漂移](figures/02_historical_progress_drift.png)：控制端点曲线，
  各attempt固定参考分别保留；71.9秒质量告警与110.270833秒确认抓持丢失分别标出。
- [适用目标误差](figures/03_historical_applicable_errors.png)：只画入口区域及
  同attempt路线证据均成立的时段，并显示原始对准阈值；阶段外不填0误差。

三张最终图使用 `historical_figures_02`，首次排版草稿保留于工程输出，不作为
最终报告图。所有7张PNG均实际显示检查；完整三路H264副本均已解码，HTML除
视频路径绑定外的全部数值与源HTML完全相同。详情见
[视觉与数值核对](visual_qa.json)。本轮没有另行声称完成浏览器交互回归。
