# 5e2a3de 的 CI 失败复现

GitHub CPU contracts #29 对冻结提交 `5e2a3deb4ddf0f7766cf9a0721415549b53019ec` 实际失败，contracts 步骤退出 1，normal-readers 通过。

在已有独立 CPU 环境复现同一 workflow 测试选择：**549 passed、11 skipped、1 failed**。唯一失败是 `test_wrist_changes_fixed_aim_only_and_keeps_global_side_view`，仍要求新版 side camera 与历史 Project_v1 完全相同，与此次已授权且已检视的 side v3 参数变化冲突：eye Z 1.65→1.32 m、target Z 1.0→1.05 m、focal 2.0→1.7 cm。

这是旧配置合同没有同步的测试失败，不能回退相机或宣称整套 CI 通过。后续修订测试的结果保存在独立目录 `../ci_5e2a3de_contract_fix/`，本目录失败日志、JUnit 和逐项结果保留原样。测试过程没有修改源码，未启动 Isaac/GPU/API。
