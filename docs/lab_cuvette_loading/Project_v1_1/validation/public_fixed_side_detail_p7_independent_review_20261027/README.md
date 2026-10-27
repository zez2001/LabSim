# P7 固定侧视细节独立审查

最终 entry/profile/tests SHA 见 [review.json](review.json)。未发现剩余阻塞；这是候选实现与离线证据审查，未实际发送 P7 或执行任务。

独立 focused39/39 通过；作者 full CPU 的717通过/13skip/0失败也已读取 XML 与 SHA 核对，不冒充我重跑了全套。原 P4/P6 假 transport wire 对 frozen58da 一致，旧 helper/profile SHA 保持；3行 dispatch 带来的组件 SHA 变化真实记录。

实际 D24 source JPEG 的固定 ROI[240,32,520,312]，独立 Pillow12.3 裁图/缩放/编码与保存派生 JPEG 逐字节一致。像素中心 A 与 K_new=A*K 核对通过；原 CURRENT 五块不变且最后，最终3–4图最多一历史腕图，context2是一组完整 response/tool receipt。

独立重跑25帧公开 bound 审计，public63462、private conservative67829、原80k下最小余量12171。它只覆盖这批已闭合源，不保证未来请求；实际最终 payload 仍由原 client 在网络前检查并预留原共享预算。$30/1500/80k/1024及动作限额不提高。

此前 offline preview 的 proof 身份未绑定和输出可嵌入原 run 两个问题已局部修复，重复--output/冲突/旧 proof 兼容及全 run 输出重叠负例通过；无 live P7 payload 变化。实际 D24 仍明确 API_sent=false，pre_detail 为中间准备，旧5图探索不能代替最终4图包。

本次还核对 [pixel proof](pixel_and_preview_verification.json)、[独立bound](independent_bound_verification.json)、[组件metadata](controller_metadata_snapshot.json)和 [focused XML](focused39.xml)。P7同时改变ROI细图、历史选择、context和提示，不能称单因素对照；没有提供安全高度、障碍/座坐标、专家路线或自动动作，也没有证实能避免碰撞。
