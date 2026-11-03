# 便携证据复算

`analysis/` 是最终分析 `analysis_final_02` 的逐字节副本；`metrics/`
保留原机器上的正式trial、成本和初态身份。`episodes/` 是四条正式记录的
原result、独立评分、collector资格及元信息小文件，未重写标签。

`portable_trials.json` 是独立命名的派生清单，将四条已启动记录绑定到包内
`episodes/`、`metrics/costs/`、`../validation/` 和 `../cases/*/progress/`。
20项计划、4项启动与16项未启动不变；这不产生新的策略试验。
`source_binding.json` 保存复算输入的原来源、SHA256、未打包H5的身份和范围。

工程反馈包中，使用已有 Python 3.11 和 NumPy：

```bash
PYTHONPATH=code python code/docs/lab_cuvette_loading/Policy_eval_v1/tools/reanalyse_portable.py \
  --package-root . --output /absolute/path/to/NEW_RECOMPUTATION
```

输出目录必须不存在。工具验证全部绑定文件、完整逐步Progress、事件和
gzip转移凭据；在新的 `derived_evidence/` 工作副本中，只将summary所记录的
gzip1存储SHA/byte数重绑定为已经验证解压字节相同的gzip9转移副本。
除了这两个存储表示字段，summary所有字段逐项相同；包内原始summary和
scorer/资格文件保持原字节。派生工作副本与核对凭据会保留在新输出目录。

`analysis/` 新输出应与最终分析02的全部分组结果及逐集任务、阶段、连续量、
漂移、尝试、成本和时间指标相等。原始H5缺省不在反馈包内，工具不打开H5，
不从原物理轨迹重新运行scorer，也不重做cooked几何验证。H5结构与视频解码
等原实验闭合证据在 `../validation/`；如需重新核验，须取回来源绑定中列出的
工程端原始文件。取得相同表格不产生新的真实模型或物理实验结果。
