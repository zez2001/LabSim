# 公开腕部历史图像输入适配

本实现是 **未做模型或物理验证的候选输入适配**。CPU 测试不能证明下一次装载成功，也不改写 GPT04 的真实失败结果。它不增加动作宏、自动恢复、成功判断、GT 检测器或训练功能。

## 显式入口与兼容性

新增 profile：`config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high_temporal.json`。它与已有 `context4_640high` 的唯一区别是 `visual_context` 字段；模型、low reasoning、1024 输出 token、图像编码、动作上限、共享预算、次数、超时等参数均保持原值。只有显式选择它才启用适配。

```bash
LABSIM_POLICY_DIR=config/lab_cuvette_loading/Project_v1_1/policies
./labsim eval --project-version Project_v1_1 --scene standard \
  --backend gpt6 --episodes 1 --headless \
  --provider-config \
  "$LABSIM_POLICY_DIR/cubence_gpt6_context4_640high_temporal.json" \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_temporal_NEW
```

以上仅为复现入口示例，本次没有执行该命令。使用新的输出目录，避免覆盖原运行。

已有 profile 缺少 `visual_context` 时继续原 prompt4、原工具类及原 client；只有新 profile 走 prompt5 和 `PublicTemporalVisualClient`。旧 `cubence.py`、共享 `cubence_tools.py`、Project_v1 和仿真运行时均未修改。

## 输入与参考选择

当前公开状态与双图的五个内容块保持原样，仍是请求的最后一个 user item。最多在它之前插入两张历史腕图及相应公开机器人状态、双指接触、时间、腕相机标定：

- 上一条具有不同 observation ID 且仿真时间前进的公开观测。
- 本集首次公开双指接触参考：只使用两个有限 `finger_contact_N >0.02 N` 的公开值。它是首个满足条件的 **决策观测**，不是首次物理接触，不要求物理持续，也不保证成功抓取。

相同观测帧兼任两种参考时只发送一次历史图，记录两个角色。反复 `observe` 同一 ID 不覆盖前一不同观测或首次参考；新的 episode 清空记忆。没有历史时仍只有当前双图，最多总计四张图。

历史图只是附加输入。它的 ID 被明确标为过时身份；下一动作必须使用最后当前观测中的 ID。历史标注说明同像素不等于相同世界位置，参考不代表器皿三维状态、插入深度或承托。

prompt5 提前要求对照杯口、黑色指垫和座缘：TCP 到位不等于器皿跟随。若下降时杯体相对手指上移、接触变为单侧或看不到预期进展，应停止继续累计下降，选择有视觉依据的安全回退或结束；动作依旧由模型通过原通用工具决定。没有将 GPT04 的离线接触时间、XY 偏差、物体真值或 teacher 阶段放入输入。

## 预算与时序

装饰器只代理既有 client 的 `cfg/ledger/responses`。输入在调用原 `responses()` **之前**扩展，因此原 `CubenceClient.request()` 的上下文上界检查、共享账本预留、HTTP 重试和总费用上限会看到全部新增图像。没有额外 API 调用，没有重置账本，也没有推进物理时间。

新增图像会增加上下文与费用。原 80k 本地保守上界及 30 美元/1500 次限制不变；达到限制就保留失败，不悄悄删参考图、裁断工具组或提高限额。真实费用及闭环效果仍需一次实际运行验证。

## 记录与隐私

原有当前观测 JPEG/JSON 仍由共享 runner 保存。适配器核验这些字节与实际当前输入一致，避免重复编码。新目录为每个请求保存 `temporal_visual_context/decision_NNNNNN/`：

- 历史腕图的 exact JPEG，以及其最初已编码公开 JSON。
- current、previous、contact-reference 的 episode/observation ID、源 decision/request label、时间与 SHA。
- 按实际顺序保存的 `input_items_public_projection`：公开 text、工具调用和回执保留；图片替换为相对文件路径和 SHA，可由 `reconstruct_input_items()` 复原。
- 实际完整 input_items 的 canonical SHA、公开投影 SHA、是否可以重建完整输入。
- 委托返回或失败的安全 outcome。空/无效观测在调用 provider 前记录安全错误码，不保存未验证内容。

完整 response-item 工具组 **在实时请求中原样保留**。其中若含 reasoning、encrypted 或未知 opaque provider item，则文件仅保留类型、位置与哈希，不保存私有内容；此时明确记录 `exact_full_input_reconstructable=false`。没有这些私有项时，CPU 测试实际从保存图片/文本重建输入，并与完整 wire-input hash 一致。这里的 wire-input 指 `input_items` 参数，不是 HTTP body、HTTP headers 或账户账单；不宣称隐私项可以从阅读包复原。

每次请求证据用独立目录且拒绝覆盖。API 失败也保留事先保存的输入清单；不写 token、请求头、provider 错误 body 或隐藏推理。

## CPU 验证与边界

实际定向选择为 **77 passed**；完整现有 CI contracts 为 **609 passed /11 skipped /0 failed**，检查期间源文件未变。证据位于 `validation/public_temporal_context_v1_20261027/`。测试使用本地 fake opener、临时账本和合成公开 RGB，不调用网络、GPU 或物理仿真。

覆盖旧 profile 原样转交、显式新 profile、固定首次公开参考、重复观测、跨 episode 清空、参考去重和最多四图、current 最后且身份不变、时间不一致拒绝、JPEG 与原公开 JSON 精确字节、工具组原序保留、私有项不落盘、公开输入完整重建、篡改检测、失败记录以及原客户端按新增图像预留预算。指令本身不能补足遮挡，也不保证模型识别滑移。首次接触参考可能仍在来源架内；正常闭爪形变与后续相对运动需由模型结合当前图像、动作与触觉判断。
