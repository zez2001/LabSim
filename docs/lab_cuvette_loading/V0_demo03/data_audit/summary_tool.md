# 可重复生成的结果汇总

`demos/lab_cuvette_demo03/summarize.py` 只读既有输出，创建新的 CSV、JSON 和 SHA256 清单。不重新判分、不改成功标签、不复制大体积原数据。

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.summarize \
  --roots outputs/lab_cuvette_loading/V0_demo03/dev_01 \
          outputs/lab_cuvette_loading/V0_demo03/FIXED_BATCH \
          outputs/lab_cuvette_loading/V0_demo03/RANDOM_BATCH \
  --output outputs/lab_cuvette_loading/V0_demo03/NEW_SUMMARY_DIRECTORY
```

将示例 FIXED_BATCH、RANDOM_BATCH 换成本轮实际目录。每次选新输出目录，已存在的目录会被拒绝。根目录重复或重叠时，同一 trial 只统计一次。缺失的根目录会明确列出，不生成假 episode。

输出：

- `episodes.json`：全部 episode、独立成功/失败/未判分/未执行计数、原始控制器及 writer 资格、逐文件 SHA256 和来源。
- `episodes.csv`：阶段、失败点、槽位、布局扰动、已观察最大源几何穿透、末深度、撤离后窗口、时间、录像和 H5 路径等。
- `manifest.json`：本次汇总代码和输出文件哈希。

独立判分驱动 workflow/data_eligible 计数；controller、adjudication 和 H5 标签分列，三者不一致会告警。`independent_and_writer_data_eligible` 仅表示独立判分和 writer 资格标签同时通过，不表示数组检查或实际 batch 已通过；后者仍须运行 `data_check`。未执行和未判分不冒充物理失败。没有撤离后观察时相关数值为 null，最后记录只叫 terminal_window。CSV 空单元格表示不可用，JSON 的 null 为规范表示。原 CAD 配套及真实校准在本模式下保持 false。

初次验证用真实 dev_01 运输碰撞失败，以及真实 preflight_root_01 静态检查：两个记录中实际执行 1 条、物理失败 1 条、未执行 1 条、成功 0 条。重复根目录去重、旧输出保护、H5 哈希未变和缺测不补零检查均通过；最终证据见 `summary_tool_final_validation/`，此前接口迭代验证保留为历史快照。这只是汇总工具的验证，不是后续完整批次的最终实验统计。
