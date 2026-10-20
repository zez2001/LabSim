# V0_demo03 单次运行阅读媒体

结果：**WORKFLOW_SUCCESS**；原始状态 `WORKFLOW_SUCCESS`。仿真结束于 61.750000 s。完整主录像为 `main_h264.mp4`，它来自同一次运行全部原视频帧，没有拼接其他尝试。

各阶段片段按保存的events边界提取；未执行阶段在provenance中为unavailable，不会生成虚构片段。末段慢放仅重复播放原帧，没有增加仿真状态。固定近景相机可能不拍到来源抓取或手臂碰撞，应结合全景。

原episode：`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00`。逐文件SHA256、实际帧区间、结果标签及命令见 `provenance.json`。原CAD配套和真实标定结论未被媒体制作改变。

## 本条画面检查

本条为dev_03的61.75 s成功物理运行，独立15项检查通过；主片1853帧、30 fps，末画面对应61.733 s。来源片段从RESET 0录到TRANSPORT 20.5 s；其后片段均按实际events边界取自同一次运行。

主镜头能够呈现抓取搬运及开盖腔口，但白架最靠近镜头的一角略被下沿裁切，未补画。腔内A适配座、慢松爪和撤离用固定近景核验。视频与原媒体并列图仅作角色对应；原任务A1/F6没有已确认的实物编号，本图ID为工程配置。详见comparison_provenance.json和media_visual_QA.json。
