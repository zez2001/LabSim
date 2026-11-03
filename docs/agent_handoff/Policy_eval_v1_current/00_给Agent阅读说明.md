# LabSim 冻结策略评测：工程反馈包

先读 [RESULTS.md](RESULTS.md)，再打开 [GPT6 第1集 Progress 与双视角录像](cases/gpt6_01/progress/progress_report.html)。本包集中提供本轮方法、真实结果、复算代码和证据。中文详细 DOCX 与四段完整双视角视频另放在独立汇报包。

## 结果与范围

- 任务：`lab_cuvette_loading / Project_release_v1 / standard`，Progress v1.2。冻结原场景、原目标座、10×10×67.5 mm 器皿尺寸假设与20 g工程质量；本轮不训练或调整策略成功率。
- 计划 GPT-6 direct 10 集、π0.5 10 集；在原调用费用硬上限内，实际启动并关闭各2集，其余各8集单列未启动。预检诊断、历史 Teacher、历史 GPT 与 π0.5 不进入正式分母。
- 原独立 scorer 的完整任务结果均为0/2；每组 Wilson 95% 区间为0至0.6576197725。GPT 第一集实际抓持、离架和持物横移50 mm后主动结束；第二集预算截断。π0.5 两集均安全碰撞终止。
- 四集均未到达固定预插入区，未插入、释放或撤离。装载精度、有效插入深度和释放后稳定时长为 N/A；最大有效插入进度为0。成功完成耗时样本数为0。
- 这些记录描述同一标准场景中两套冻结执行方案的实际表现。样本量与预算截断写入分母和报告，结论不外推为其他模型、场景或真实仪器的普遍成功率。

## 建议阅读顺序

1. [结果说明](RESULTS.md)：完整结果、分母、阶段、成本、未完成原因和复现命令。
2. [使用指南](guide/README.md)及[冻结协议](config/lab_cuvette_loading/Policy_eval_v1/protocol.json)：任务、版本、170秒仿真上限、安全、调用预算与执行顺序。
3. [GPT身份](protocol/gpt_identity.json)、[GPT输入与工具](protocol/input_contracts.md)、[π0.5身份](protocol/pi05_identity.json)及[π0.5输入契约](protocol/pi05_input_contract.md)：模型、checkpoint、输入差异和原生动作语义。
4. `results/`：正式20项trial清单、逐集CSV/JSON、自动汇总、六类图表与来源定位。实际启动只有4集，未启动项没有伪造轨迹。
5. `validation/`：原scorer与H5闭合、完整事件重放、时间邻接、输入审计、测试及图表视觉检查。最终分析为 `analysis_final_02`；01结果保留于工程历史，用于追溯释放后统计适用性修正。
6. `code/`：本轮封装、量化分析、图表和审计工具，以及对应测试。完整可运行仿真项目从固定提交的GitHub代码获取；本包不包含Isaac环境、模型权重或大型H5。

## 在其他机器复算本报告的数字

包内 `results/portable_trials.json` 是明确标注的派生相对路径清单，原机器身份仍保留在 `results/metrics/trials.json`。使用已有Python 3.11与NumPy，在本包根目录运行：

```bash
PYTHONPATH=code python code/docs/lab_cuvette_loading/Policy_eval_v1/tools/reanalyse_portable.py \
  --package-root . --output /absolute/path/to/NEW_RECOMPUTATION
```

输出目录须不存在。工具读取原result/资格JSON及全部Progress，验证gzip转移前后解压字节相同；仅在新输出的派生工作summary中更新压缩表示的SHA/byte数，包内原summary、stage和scorer/资格标签不改。它核对全部分组及逐集关键指标与最终分析02相同，不打开H5，也不替代工程端原物理、接触和H5结构核验。[复算范围说明](results/PORTABLE_REANALYSIS.md)提供详细身份与限制。

四条正式轨迹均提供完整Progress、事件和侧／腕连续视频，HTML可分别打开：

- [GPT6 第1集：抓持、离架和横移](cases/gpt6_01/progress/progress_report.html)
- [GPT6 第2集：费用预算截断](cases/gpt6_02/progress/progress_report.html)
- [π0.5 第1集：安全碰撞停止](cases/pi05_01/progress/progress_report.html)
- [π0.5 第2集：安全碰撞停止](cases/pi05_02/progress/progress_report.html)

HTML使用与真实仿真时间关联的双视角播放器。播放器无法定位时，可用支持HTTP Range的本地静态服务器打开阅读包。H264视频是原记录的显示副本；每案 `media_receipt.json` 和 `progress/portable_media_receipt.json` 保存来源、时长、帧数和哈希，未拼接不同试验。

## 核对与后续接手

使用 `valid_insertion_progress` 或 `effective_continuous` 阅读有效进展；旧 `insert.continuous` 是兼容的原始投影诊断。`held_transport_50mm` 与到达预插入区域分别统计。未进入适用区间的指标保留null/N/A，未达成阶段没有加入0秒平均。

GPT第一集的approach确认采用有效物理抓持证据；TCP到配置抓取参考点的最近距离是独立几何诊断，不能据阶段达成反推出它小于5 mm或称作接触点精度。详细定义和源码位置见结果说明。

原资产、物理、控制、动作转换、reward、独立scorer和数据资格未改变。运行源码为 `3ca253324b1ec540ae5ec07f2110c9c091f6ddd1`；最终分析为 `094f8a18ecf0858dee4b8c86e9133c7275520995`。新分析只修正释放后稳定指标的适用范围，没有重跑策略或改变原始标签。

[publication.json](publication.json)记录发布、CI和运行／分析版本；[protection_final.json](protection_final.json)记录源文件与历史保护检查。`文件清单.json` 和 `SHA256SUMS.txt` 由打包脚本生成。大型H5、原始模型输入与详细日志留在工程端，包内结果和闭合凭据提供episode身份、路径及SHA256。

开发分支：{{BRANCH}}
最终发布提交：{{SOURCE_COMMIT}}
打包时间：{{GENERATED_AT}}
[固定提交完整源码](https://github.com/zez2001/LabSim/tree/{{SOURCE_COMMIT}})
