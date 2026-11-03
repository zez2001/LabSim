# 历史 gpt_debug_04 策略身份与独立恢复

本目录精确指向历史运行 `gpt_debug_04`，不是把“第4次运行”解释为某个默认 P4 配置。原运行和本次核查均保持原始身份，机器凭据见 [identity.json](identity.json)。

## 原运行身份

- 原目录：`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_04/episode_0000`。
- episode UUID：`28bd2fc2-7bd7-44ee-9fb6-aaff53cbc99d`。
- 原任务版本：`Project_v1_1 / standard`；原执行提交：`63410bf9258ba2f9bd0af4d517194523fca6617c`。`process_exit.json` 和 `release_metadata.json` 的执行身份一致。
- 原临时运行 checkout：`/tmp/labsim-project-v1-1-clean-20261027`。该绝对路径是历史身份，不改写为当前目录。
- 原实际参数文件：`config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high.json`。原进程命令直接记录了此路径；它与当前同名配置逐字一致。

该配置是 v4 通用机器人工具、context4、640/high 双图。发布版默认 `cubence_gpt6.json` 是 context12、512/low；此前定量评测采用的P9另有时序腕图、固定侧图detail、active-view提示和机器人self-state。三者应分别标识。

## 冻结的策略内容

请求模型为 `gpt-6-astra`，Cubence HTTPS `/v1/responses`；51份原策略trace中的返回模型标识均为同一字符串。中转服务背后的权重身份不能由服务标签独立核实。

使用 `ProjectV11RobotTools`，prompt版本 `Project_v1_1.public_tools.v4`。工具仅 `observe`、`move_ee`、`gripper`、`wait`、`finish`，无抓取、搬运、对准或插入专用动作。所有动作仍由环境作连续IK、实际执行与安全检查。

关键SHA256为：

```text
原配置文件：
650301fda097d73e41c5520438228d66acf4bab0437b6d351464046cf3c3a2d5
原SYSTEM_PROMPT：
ac9ac4d33b2e329dfe684bfcd8461b4962274ac5b57659c94194da2af0ce2ddf
实际instructions（原prompt + Action limits，按原构造器重建）：
829f54e345e4b2343cdd433f21fb57a559ce60b7fd65a0ee5b393acf22e0c46d
原工具schema（canonical JSON）：
d0f8634840a59594da8c62d92d98dbf4ae91cb64421cb6c975375350efffedeb
```

原参数为 low reasoning、最多1024输出tokens、80k保守输入上界、请求超时120秒、最多2次网络重试、单集墙钟1800秒、正常单集最多160次模型调用。temperature和策略seed未发送。context4对应最近两个完整的response/tool-receipt回合；每集重建工具和空history，不保留跨episode结果记忆。

当前侧视与腕视RGB经Pillow LANCZOS最大边640、JPEG quality60、high detail发送；原51次实际双图均为640×480。没有历史图像、固定crop、时序接触参考、active-view扩展或机器人自身FK附加包。每次读取当前公开观察后才决策；恢复配置不会回放原51个动作。

## 原输入与信息范围

51份原公开状态JSON、51份artifact manifest及102张实际发送JPEG的SHA全部核对通过。当前公开状态包含机器人关节/TCP、夹爪开度与力上限、双指触觉、相机标定及时间、槽位和目标座ID、任务文本。按禁用评测字段精确键递归扫描，未发现器皿真值、精确孔口误差、Teacher waypoint、Progress、scorer或reward字段。

任务文本包含静态名义几何与机器人标定：A1取物、F6蓝色干扰物、内部A座、10×10×67.5mm器皿、27mm装载深度、终态40.5mm露出长度及hand/TCP固定变换。原完整文本及其SHA保存在身份JSON中。当前 `get_task_language` 的任务源码与原提交逐字一致，不能漏掉这些原静态instructions，也不能额外加入动态器皿或座位姿。

`finish`只是请求独立判分并结束；最后评分不会作为后续模型输入。原公开动作拒绝选择私有metadata/阶段。接触锁存、IK和机器人安全监测属于环境通用执行功能，没有Teacher接管或隐藏动作路线。

该历史版本尚未保存P9式完整wire manifest。原prompt、工具、配置、当前状态文本及精确JPEG均存在；前两个回合中只留在内存的供应商reasoning item未被序列化，因此不能独立重建完整历史HTTP字节序列。实际instructions的哈希来自原版本逐字相同的请求构造器及保存的prompt/config。

## 原实验结果保持原判定

实际运行51次模型调用／51次网络请求，没有协议拒绝：48次move、2次gripper、1次finish。原策略墙钟1319.609秒，仿真114.716667秒，6882个控制步、27532个物理步。返回usage记录输入375584、输出8383 tokens；原估算费用USD4.17499，供应商实际账单未知。

原最终结果是 `task_success=false`、`failure_type=GRASP_SLIP`、`record_valid=true`，未释放、未撤离。原终态 `grasp_success=false` 和 `transport_success=false` 保留。原物理事件另外观察到：双侧抓持候选14.1125秒、来源槽清出15.5625秒、持物横移约50.08mm在32.508333秒。历史事件证据与原最终资格分别说明，不能将中间动作改标为完整成功。

## 独立源归档与当前差异

完整原策略已逐字复制到 [独立vendor目录](../../../policy/backends/gpt_debug04_v1/vendor/)；[source_manifest.json](../../../policy/backends/gpt_debug04_v1/source_manifest.json)保存每个原Git blob、SHA256、大小及依赖关系。独立配置为 [provider.json](../../../config/lab_cuvette_loading/Gpt_debug04_v1/provider.json)，与历史配置原字节一致。

三份vendor文件仅相互相对导入，不依赖共享P9模块。依赖闭合为Python标准库、观察JPEG编码所需Pillow及调用方注入的环境facade；vendor不导入Isaac或模型SDK。`ProviderError`、`CubenceClient`、`BudgetLedger`必须全部取自同一vendor命名空间。

与当前共享实现比较：

- `cubence_tools.py`原字节完全相同；原v4 prompt、工具schema、`ProjectV11RobotTools`和回执筛选的AST一致。
- 当前 `cubence.py`新增可注入config validator，默认仍是原validator。
- 当前v1.1工具模块增加P6–P9可选路由；本原profile不含这些启用键，仍走原v4路径。
- 当前task executor、facade、连续IK、gripper hold和robot tracking源码与原提交逐字一致。`Project_v1_1/standard.yaml`仅两处Teacher版本标记v6→v7；外部GPT分支不执行Teacher控制器。

本次恢复保留共享策略、P9、CLI、物理和原记录。原配置中的费用／请求硬上限也原样保存；该审计和复制不授予新预算，不创建客户端、不读取凭据、不发网或运行GPU。若另获授权调整资金上限，应在独立且可追溯的预算桥中处理，不能修改vendor原文件或悄悄重置历史账本。
