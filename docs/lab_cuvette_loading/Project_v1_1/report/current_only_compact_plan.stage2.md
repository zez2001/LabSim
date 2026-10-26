# Stage2 current only 阅读包预算

这是静态准备方案，未复制、转码或打包任何大视频。硬上限按 **80,000,000字节**，不是80 MiB。最终取材等待新run实际关闭和独立判分；active teacher_preload01/GPT03不读、不预填结果。七页报告输入为 `release_inputs.stage2.draft.json`，仍finalized=false，没有author/marker/渲染。

建议分配：报告2MB；必要CSV/JSON4MB；代表episode公开观测与exact JPEG5MB；配置/首读/版本/校验2MB；最终GPT全程20MB；最终teacher全程20MB；当前GPT02完整失败14MB；诊断或力不足失败4MB；少量关键近景4MB；预留5MB，总计80MB。

公开观测留档不等于完整HTTPbody或完整memory response-item组，不宣称私有推理已保存。模型JPEG保持原始编码字节；不能为减包再次压图后仍称exact输入。其它正式集可保留原分数、controller/trace/receipt及图片SHA，明确未随包图像的来源范围，不伪造可访问的GitHub输出链接。

## 当前关闭媒体候选

- GPT02整条dual-view：13,358,060B，59.900秒，1797帧，1280×480，30fps；适合当前座口受阻/释放后几何安全失败代表。
- slow_close01整条dual-view：3,853,058B，20.000秒，600帧；可作为实际保持力不足的完整短失败记录。
- grasp04整条dual-view及新teacher/GPT最终录像根据最终预算选择。grasp04只是持物诊断，不标完整装载成功。
- source_hold01整条dual-view：23,483,982B，124.300秒；仅作teacher候选备选，不与最终teacher录像重复塞入。即使工作流到末段，原任务仍GRASP_SLIP。

上述仅核实体、关闭证明及ffprobe容器参数，没有执行全视频解码/视觉QA，也没有重新哈希大媒体。具体grasp04元数据与所有proof SHA见JSON。最终选择后须复核源视频SHA、全解码、实际帧数/时标、关键动作及与原评分一致性。

## 控制体积而保留完整性

主录像从reset到实际结束保持同一条连续运行，不拼接不同尝试，也不剪掉失败前段。优先直接采用原文件；必要时在最终取材阶段生成有来源SHA的有损演示副本，保留原持续时间、帧数与时间戳，并做完整解码/视觉核验。近景片段只补充主录像，不替代它。软预算可借用5MB预留，但成包后仍严格核全部文件总字节数。

只选一个主要同步双视或单次连续合成视角，不把每run的side、wrist、dual和重复主片全部复制。报告必要CSV优先保留：原异常7动作对照、GPT02受阻/支撑/释放全曲线、33动作表、slow_close01力/开口与双层派发表。完整H5、raw/gzip、环境、权重、原始附件和assets全集不入阅读包；源码从最终固定GitHub提交，资产从固定HF revision取得。

旧Project_v1/Env_v1/Size_v1报告与大视频仅固定SHA链接，不重复复制。本轮产生的诊断对照仍可选必要图/CSV。最终文档引用的本地媒体、图、配置、表均须实际随包；DOCX/MD保持相对层级，原H5等只作明确provenance，不伪装成包内实文件。先完成最终提交/远端CI/HF与报告QA，再新建桌面小包、核所有链接/SHA和≤80MB体积。
