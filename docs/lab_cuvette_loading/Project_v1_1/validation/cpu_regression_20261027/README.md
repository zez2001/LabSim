# Project_v1_1 当前工作树 CPU 回归

日期：2026-10-27。按现有 `.github/workflows/cpu-contracts.yml` 的两个测试选择执行，无依赖安装、Isaac app、训练或外部模型调用。检查HEAD为 `21a0c7e44f2c7e1742a802b1acf27a5082586436`，同时包含当时工作树改动；不是最终提交的远端CI或物理验收。

轻量contracts：346 passed、11 skipped、0 failed，5.56 s；bash入口语法及CLI help也通过。跳过记录包含9个data方法与2个模块收集跳过。补充normal-readers：22 passed、0 skipped，1.61 s。合并两个runtime后，368个不同具体用例至少通过一次，跳过范围全部补齐。

轻套分组：旧版及共享214 passed /1个模块skip；新旧版本路由11 passed；Project_v1_1专属121 passed /10条skip记录（9个方法与1个模块）。具体身份、模块skip覆盖映射见[摘要](summary.json)，不能把模块级skip误算成一个已执行测试。

新旧测试均覆盖：CLI默认与显式版本、历史入口、资产锁/样例/数据读取、teacher/scorer状态机、Cubence旧接口和新receipt adapter、新IK/执行回执/夹爪保持/机器人tracking、正常ACT/DP读取及诊断排除。CPU通过不证明真实抓取、插入、物理稳定或GPT成功。

[contracts完整结果及源码SHA](contracts_result.json)、[reader结果及源码SHA](normal-readers_result.json)、[contracts JUnit](contracts_junit.xml)、[reader JUnit](normal-readers_junit.xml)、[runtime版本](runtime_versions.json)。所列测试依赖文件在每次执行前后哈希一致。

contracts使用既有轻量环境；reader使用既有h5py/Torch环境并设置CUDA_VISIBLE_DEVICES为空。reader的OpenCV4.9、zarr3.1及Torch CUDA构建与CI固定的OpenCV4.11、zarr2.18、CPU Torch构建不同，实际张量和检查均在CPU执行。这是现有环境兼容证据，不能当作对应远端CI已经完成。最终冻结提交须再核对其实际CI结果。
