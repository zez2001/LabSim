# 接触保持 v2 的 CPU 回归及保护检查

本轮实际检查提交 `b3765fcea3f3e24b75fb42eb5e3ef6ed8c5795e6`。测试时被监测的源码 SHA256 前后相同。使用已有独立 CPU 检查环境与已有 labutopia Python，均设置 `CUDA_VISIBLE_DEVICES=""`；未安装依赖，未启动仿真或调用模型 API。

- 当前 CI 契约选择：505 项通过、11 项跳过、0 项失败。跳过包括 9 个需要正常读取环境的用例，以及 2 个依赖缺失的模块级收集。
- 已有 labutopia Python 的正常读取选择：22 项全部通过，包括上述 9 项用例、5 项 reader CLI 用例和 8 项便携样例用例。两个模块级跳过均在此环境实际收集并运行。两组选项合计 527 个实际通过用例。
- 重点状态机、旧夹持、关节语义与跟踪集成选择：68 项通过；其中用例已包含于完整契约回归，不另行累加。
- 596 个历史资产本地字节全部与基准 Git/LFS SHA 相符；实际运行所用独立便携缓存 83 个文件全部符合锁定 revision `bb880f098180c291f6f65995f969d48047207067`。
- 相对历史基准，旧配置、实现、资产及旧发布证据的受检 Git 范围无修改。相对新版本基准 `21a0c7e`，acceptance、demo_release、physics、robot、vessel、gripper、executor 七组配置和三个独立评分实现未改变。

`contracts_result.json`、`normal-readers_result.json` 保存逐用例、命令、时间、源码哈希和真实退出码；对应日志和 JUnit XML 均保留。`protection.json` 说明受检范围与边界。历史源资产保留原始出处字节，便携发布副本清除非执行的作者路径，二者有不同哈希；因此不能将历史源码目录当成已安装的便携资产根目录。保护结果按实际闭合运行的资产根目录核实。

独立旧反例复核见 `../../diagnostics/force_hold_v2_review_20261027/README_REVISED.md`。此次为软件机制、读取接口及保护检查，不能代替新的物理抓取、释放、完整任务或真实标定验证。新公共 joint 语义修复仍只有 CPU 证据，本轮没有新增物理 joint-policy 测量。

复现入口为本目录 `run_cpu_checks.py contracts`、`run_cpu_checks.py normal-readers` 及 `check_protection.py`；脚本拒绝覆盖同名既有证据。环境路径仅用于复现本机 CPU 检查，不是任务运行资产依赖。
