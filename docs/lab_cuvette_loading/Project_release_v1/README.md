# Project release v1 使用与验收

这是独立的 `Project_release_v1` 环境发布版本，物理任务继续使用 Project_v1_1 的固定 standard 场景、10 mm 比色皿、20 g 假设质量、原 A 座及已验证的执行器与评分器。历史结果不修改。本轮验收以环境是否能连续交互、闭合数据和正常读取为目标，不以策略装载成功率为门槛。

[项目快速开始](../../../README.md) · [生命周期和数据闭合](lifecycle.md) · [外部策略契约](external_policy/contract.md) · [物理基线 Project_v1_1](../Project_v1_1/README.md)

## 当前实际状态

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 代码与远端 | 运行代码 `122c4c0` 与远端一致；CPU CI成功 | [GitHub实际查询](validation/github_122c4c0_actual.json) |
| 资产与独立缓存 | 固定revision，83文件hash通过；不新增资产 | 本轮发布清单补充实际缓存证据 |
| GUI与退出 | 官方CLI短程受控结束，退出0；旧菜单`get_stage_state`异常未出现 | [实际退出记录](validation/gui_finish_02_shutdown_actual_20261027/receipt.json) |
| GUI剩余问题 | `ManipulatorFactory`卸载回调仍有NameError；不是无错误退出 | 同上，保留完整日志扫描边界 |
| 单集数据闭合与读取 | GUI短集已闭合；正常读取和筛选检查通过 | [闭合审计](validation/gui_finish_02_data_closed/summary.json) |
| 同进程三集 | **进行中，尚未闭合** | teacher → early_finish → reset后teacher |
| 连续真实外部策略 | **待执行或闭合** | π0.5既有部署与正式RPC；不训练 |
| 性能与体积 | **完整teacher测量待闭合** | 不用短集外推完整任务收益 |

状态仅反映本页更新时已闭合证据。CPU测试、接口存在、动作请求被接受和历史单集成功不能替代本轮连续物理运行。

## 显式版本和记录模式

所有新版运行命令保留 `--project-version Project_release_v1`。省略版本仍运行旧 `Project_v1`，不自动迁移历史输出。

```bash
# 已实际执行的GUI启动与正常结束检查，非完整teacher装载
./labsim demo --project-version Project_release_v1 --sequence early_finish \
  --gui --record-mode eval \
  --output outputs/lab_cuvette_loading/Project_release_v1/gui_NEW

# 同进程三集验收；实际结果需等待当前进程闭合
./labsim collect --project-version Project_release_v1 --headless --record-mode collect \
  --sequence teacher early_finish teacher \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_NEW
```

`--sequence`是明确的teacher/生命周期验收序列，不是零样本策略控制或任务宏。`early_finish`真实推进3秒后提前结束；中间失败标签不会被后续reset改写。常规teacher、GPT及RPC入口不带该参数，沿用独立launcher；其本轮实际验证范围另记。

`collect`和`eval`当前保留完整双相机H5、原生侧视/腕视/双视角录像，物理和接触日志采用lossless gzip，移除collector重复录像；`diagnostic`保留plain日志和额外collector录像。三种模式均保持在线物理、评分及安全采样，不把eval称为无图像轻量模式。细节见[生命周期说明](lifecycle.md)。

## 读取与数据资格

必须等待Isaac进程退出并确认完成标记后读取。运行未闭合、写入失败、异常中断及几何诊断不会因目录存在而进入正式训练索引。重复finish返回既有结果；完成资格、H5与索引共用finalization ID。

正常入口为 `./labsim dataset-check --path ... --sample-filter success|failure|all_valid --policy both --output ...`。多集索引默认相对外链，移动时保留整棵collection树；它不是单文件便携H5。仅在显式选择copy模式时复制完整多集数据。本轮三集的实际索引、筛选数量、读取时延和语义核对在进程关闭后补充，不提前写成2/1/3通过。

## 外部策略与接口

真实π0.5使用现有LIBERO checkpoint，通过同一正式RPC获取观察、推理、执行有界动作、接收回执并正常结束。适配只做已声明的状态与动作空间转换，不增加器皿/目标座真值、不调用teacher。chunk未执行部分在拒绝、部分执行或终止后丢弃。模型等待时仿真暂停。完整动作与相机语义见[外部策略契约](external_policy/contract.md)。

GPT既有能力保留，本轮不优化提示词，不新增付费调用。Project_v1_1 GPT08是稳定搬运后主动结束的有效失败，不能当作本轮π0.5验收或GPT装载成功。

## 发布与已知边界

固定资产revision为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)，运行代码为 `122c4c03586abdfa7e3117c13e62f8d46f786b04`，[对应CPU CI](https://github.com/zez2001/LabSim/actions/runs/40482694086)已成功。后续文档发布提交与该实际执行提交分别记录，不把文档提交冒称已运行代码。

GUI菜单owner在USD卸载前关闭，真实短程运行未复现旧`get_stage_state`异常；安装扩展的另一`ManipulatorFactory`回调错误仍存在，已定位并保留。新版本不修改用户安装的扩展。原生速度与差分差异、有效碰撞烹饪表示未完整读回及未真实校准的历史边界继续保留。

没有第二台机器的部署证据。本轮不训练、不采random、不修改器皿尺寸或原座、不建设checkpoint/resume；`finish`结束当前集，`reset`建立新集。
