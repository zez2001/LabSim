# 数据用途、读取与移交

当前环境：`Project_release_v1`。采集、索引和 reader 分别管理运行意图、集合成员和样本资格。

## 1. 运行时声明用途

`record_purpose` 是用途元信息，与成功、失败及记录资格分开保存。

| 用途 | 内容 | 正常入口 |
| --- | --- | --- |
| `demonstration` | 标准 Teacher 示范 | 普通 `demo`、`collect` |
| `policy_evaluation` | 策略交互与评测 | 普通 `eval`、`serve`、GPT 控制 |
| `lifecycle_diagnostic` | 多集 reset、提前结束、服务故障等诊断 | `--sequence` |
| `resource_probe` | 明确声明的短程资源探针 | `--record-purpose resource_probe` |
| `unknown` | 历史记录或直接 API 调用未声明用途 | 显式成员清单或诊断检查 |

官方当前入口保存用途到运行清单、episode 元数据、H5 属性及结果。用途由调用者的运行意图指定；结果、时长及动作数量不用于推断用途。

## 2. 示范及评测索引

先等待 Isaac 进程结束，再建立索引。示例中的 `$RUN` 是一次已关闭的运行目录；新输出文件必须不存在。

```bash
# 正式示范集合。
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$RUN" \
  --purpose demonstration --mode relative-links --output "$RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$RUN/index/demonstrations.hdf5" \
  --sample-filter success --output "$RUN/index/success_reader.json"

# 正式策略评测集合；该模块 CLI 默认即为 policy_evaluation。
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$RUN" \
  --purpose policy_evaluation --output "$RUN/index/policy_evaluation.hdf5"
./labsim dataset-check --index "$RUN/index/policy_evaluation.hdf5" \
  --sample-filter all_valid --output "$RUN/index/policy_reader.json"

# 开发诊断：明确查看所有已完成记录，包括未知用途的历史记录。
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$RUN" \
  --purpose all-completed --output "$RUN/index/diagnostic_completed.hdf5"
```

每次索引生成同名 `.index.json`，列出：纳入和排除的 episode、已声明用途及其来源、排除原因、源 H5 相对路径和 SHA256、最终完成身份、源集合及所选集合的 `success / failure / all_valid` 数量。未知用途不会进入正式示范或正式评测索引。空集合会得到明确的零计数，reader 会报告没有合格样本。

`--purpose` 只决定集合成员。reader 的 `--sample-filter` 保持原语义：

| 筛选 | 资格 |
| --- | --- |
| `success` | 完整、有效且具备成功 BC 资格的任务成功 |
| `failure` | 完整、有效且具备失败分析资格的实际任务失败 |
| `all_valid` | 完整且有效、结果已知的任务记录 |

具体资格仍由原有记录完整性、独立判分、物理及 domain 检查确定。正式 BC 使用示范用途索引加 `success`。策略评测使用评测用途索引加相应筛选。诊断索引用于排查，不作为默认训练入口。

Python 兼容 API `build_index()` 未指定 `purpose` 时仍保留历史的 `all-completed` 行为。新调用应显式传入用途；命令行默认采用 `policy_evaluation`。

## 3. 历史数据：sidecar 绑定，保留原 H5

历史用途清单采用 `labsim.Project_release_v1.purpose_members.v1`，每个成员绑定 `episode_id`、源 H5 相对路径、完整文件 SHA256 和用途。索引建立时逐项核对；身份、路径、内容或已声明用途冲突会拒绝建立索引。原 H5、任务标签、历史评分及原索引保持原样。

复用已审查的 π0.5 成员清单：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.membership "$RUN" \
  --curated-policy-manifest docs/lab_cuvette_loading/Project_release_v1/validation/pi05_standard_01_env_closed/curated_index_manifest.json \
  --output "$RUN/purpose_members.json"
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$RUN" \
  --members "$RUN/purpose_members.json" --purpose policy_evaluation \
  --output "$RUN/index/policy_only.hdf5"
```

该历史清单明确指定 1 条策略评测及 10 条资源探针。`all-completed` 配合同一清单可查看全部 11 条；`resource_probe` 可只查看 10 条探针。清单不依据成功标签或时长重新分类。原生命周期三集可以全部声明为 `lifecycle_diagnostic`，仍按 `success / failure / all_valid` 分别读取 2 / 1 / 3 集。

显式标注自有历史记录：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.membership "$RUN" \
  --assign lifecycle_diagnostic=EPISODE_UUID_1 \
  --assign lifecycle_diagnostic=EPISODE_UUID_2 \
  --output "$RUN/purpose_members.json"
```

`--assign unknown=EPISODE_UUID` 保留用途未知的事实；只有显式 `--purpose members --members ...` 或诊断用途选择才会纳入。提供清单时，清单同时限定集合范围，未列出的记录会标为 `not_in_explicit_members`。清单中不存在于源目录的成员会报错。

## 4. 两种数据移交方式

### 相对目录树：`relative-links`

索引通过相对外链引用原 H5。移交索引及依赖文件，保持它们的相对目录关系。例如：

```text
handoff/
  index/demonstrations.hdf5
  episode_0000/dataset/episode_0000.h5
  episode_0001/dataset/episode_0000.h5
```

依赖检查列出每个源文件的完整解析路径、是否存在、身份可读性及必须一起携带的文件：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.transfer \
  handoff/index/demonstrations.hdf5 --verify-sha256 \
  --output handoff/dependencies.json
```

`--verify-sha256` 完整读取外链源文件并验证建立索引时保存的 SHA256。缺失或不匹配时退出码为 2，结果指明具体文件；补齐目录后重新检查。普通存在性检查不需要此参数。

### 单文件：`copy`

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$RUN" \
  --purpose demonstration --mode copy --output handoff/demonstrations.hdf5
```

`copy` 包含所选 episode 的完整 H5 内容，可以单独移动、重命名并通过正常 ACT/DP reader 读取。侧视与腕视的兼容相机别名保留为 HDF5 hardlink，同一组图像不会因别名复制两份。原视频、USD、CSV 及独立运行日志不在数据索引中；需要回放或实验复核时另行携带。

## 5. 活动 writer 保护的适用范围

索引建立要求源 `run_manifest.json` 中的 Isaac PID 已不存在，并只纳入事务完整的 release 记录。该保护面向同一机器上的正常关闭后处理。跨机器的数字 PID 无法建立原进程身份，PID 复用也可能误判为仍在运行；此时保留关闭凭据、完成身份及文件校验，交由维护者处理，不修改 PID 或关闭保护来绕过。完整跨主机 writer 身份和离线导入机制单独推进。

用途筛选、历史文件保护及数据移动的具体检查见 [2026-10-28 工程验收](../Internal_use_v1/20261028/data_usage/README.md)。
