# V0 demo04 本次改动与结果 精简阅读包

本包只保留V0_demo04本次改动和结果，约31 MB。没有历史版本目录、完整H5、原始接触大数据或训练数据。此前约1.15 GB大包保持不变。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。本次交付提交：`{{SOURCE_COMMIT}}`。实验代码提交仍为 `6aaae05dbfb3ad8ac04858ed49da2d5969f51a90`；本次仅调整打包范围，未重跑仿真或修改实验结果。

## 建议阅读顺序

1. [本次改动与结果](02_本次改动与配置/改动与结果.md)：尺寸、场景、控制、判分改动及未完成项。
2. [DOCX报告](01_V0_demo04报告与结果/LabSim_V0_demo04_原座装载核查报告_20261020.docx)或[Markdown报告](01_V0_demo04报告与结果/report.md)。报告中提到完整H5，是说明此前已经完成的数据核验；H5本体不在本精简包中。
3. [录像入口](01_V0_demo04报告与结果/media/index.html)或直接打开[同次连续诊断主录像](01_V0_demo04报告与结果/media/preinsert_diagnostic_03_main.mp4)、[实际观测近景](01_V0_demo04报告与结果/media/preinsert_diagnostic_03_obs256_camera2_65s_end.mp4)、[首次失败录像](01_V0_demo04报告与结果/media/failure_transport_main.mp4)。
4. [逐次结果CSV](01_V0_demo04报告与结果/results/runs.csv)、[独立结果汇总](01_V0_demo04报告与结果/results/summary.json)、[最终尺寸表](01_V0_demo04报告与结果/dimensions/dimensions.csv)及[最终配置](02_本次改动与配置/native_nominal.yaml)。

## 结果边界

本次修正12.5 mm器皿、单台仪器和朝向，选择腔内原A座，保留原12.6 mm中央参考宽。原A/B座局部凸起仍与器皿材料干涉，没有扩孔或删件。

第三条实际记录完成76.917秒受限诊断：架内抓取、提取搬运、座口上方停止、上抬保持。没有插入、支撑转移、松爪和完整撤离后稳定；固定5次、随机10次完整任务未执行。workflow_success、native_pair_success及成功训练数据资格均为false。另两条搬运失败均保留。

## 传输与复现

请传输整个文件夹或对应ZIP，DOCX中的视频是指向同级media的外部相对链接，不能只发送DOCX。`文件清单.json`及`SHA256SUMS.txt`记录来源和文件哈希，可执行 `sha256sum -c SHA256SUMS.txt` 校验。

[源码及本次交付提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。本包中的源码补丁和配置用于审阅改动，完整可运行工程及资产从GitHub获取。完整episode另存原大包与本机outputs，不默认随结果阅读包传输。
