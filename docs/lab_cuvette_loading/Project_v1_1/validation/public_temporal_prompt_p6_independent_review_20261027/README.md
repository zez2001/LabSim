# P6 提示与回顾性公开图像QA独立审查

P6主审和独立第二位审查未发现策略、GT、宏或单位阻塞；独立35项CPU通过。100µm是模型每决策下降请求的分段上限，1mm/s是提示中的速度上限，约最后1mm由静态尺寸和图像估计；不是区域自动检测、executor自动停机或100µm实际精度。默认P4和真实动作/物理/评分限制不改。

QA方案的D7按公开双侧指力顺序选择、D34为前一distinct、D35为current，7个原JSON/JPEG SHA通过；四图原640JPEG，不裁切、不重编码。已实看三腕图的杯口和黑指垫可见，但未给API、未赋正确答案，也不从图认定底部支撑。方案尚未实现真实发送，不能写成模型已通过。

审核时plan额外user问题位于current之后；建议问题只保留在QA_instructions，去掉重复末item，维持history→CURRENT最后。发送前须无tools/环境/execute/finish，只用中立observation-only instructions；沿用CubenceClient和旧ledger，allow_retry=False最多一次网络，120秒截止，失败保留未知usage预留。

离线按这两item顺序和exact JPEG构造的示意输入，其原保守上界48923<80000，加1024输出的预留约0.54043美元；没有请求、没有保存body，也不是实际费用。真实最终payload还需客户端重新计界。

QA只验证单个回顾性公开多帧的可辨认内容，不能证明P6动作遵守、完整任务成功、三维承托或100µm控制精度。若始终不能确认自由通行，100µm全27mm可能耗尽160次/1800秒/预算，不能为完成而静默放宽。取消的0native/0API等待队列不计尝试。未读H5/raw或active run，未改runtime/报告草稿，未GPU/API。
