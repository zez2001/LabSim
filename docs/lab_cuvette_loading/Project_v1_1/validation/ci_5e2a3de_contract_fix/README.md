# side v3 配置合同更新及 CPU 复测

只修改 `tests/test_lab_cuvette_project_v1_1_configuration.py`：将过时的“side 与旧版完全相同”断言改为 side v3 全配置比较，仅允许 eye Z、target Z、focal 三项变化，并核对 `Project_v1_1.side.v3_wrist.v2` 标签。另保留独立的 wrist v2 全配置比较。原有非随机化、物理、资产和任务门控合同保持。

实际再次运行当前 workflow 的完整 contracts 选择：**551 passed、11 skipped、0 failed**，源字节前后不变。比旧失败运行多一个用例，是把 side 与 wrist 合同拆成两项测试；没有删除失败条件或改变运行时配置。

这次结果对应基于 Git HEAD `5e2a3de` 的未提交测试修正，不能把原 GitHub #29 Failure 改写成成功。后续提交需重新获得远端 CI 结果。当前运行时代码、相机参数、物理、评分和 clean checkout 均未被本修正改变；未启动 Isaac/GPU/API。
