# 显式抬升对照仍发生盖板碰撞

原GPT05的前24条动作保持不变，之后预声明Z+40mm/2s、Z+40mm/2s、X+35mm/2s、wait3s。实际只执行了第一条Z+40mm以及第二条的一半：首段实际抬升39.994955mm，第二段约19.868940mm，总计约59.863895mm。第二段出现SAFETY_COLLISION，后续X+35mm和wait完全没有执行。不能写成80mm抬升已完成或已证明净空。

首次callback：physics_step12243，51.0125s；panda_link7/geometry/panda_link7对Instrument/Collision/SourceMesh5。两个原始接触点分别有+72.593um间隙/零冲量、-22.415um分离/非零冲量。控制区间结束时刻是51.0166667s，共3060控制步；51.0125是首次callback时刻，不是最终仿真时长。

baseline原X+35mm则在step11978/49.9083333s首先由panda_link6碰到同一SourceMesh5。该抬升动作改变了碰撞手臂连杆，但没有取得安全路径。

`declared_and_actual_suffix.csv`逐项区分已执行、部分执行和未执行；未执行量保持空值。`common_prefix_numeric_comparison.csv`只比较共同前24动作对应的11525条物理状态，避免拿不同动作段强行对齐。`baseline_variant_comparison.csv`为两轮结果小表。`first_forbidden_contact.json`保留完整原始callback。

该轮为0API的control_diagnostic，完整任务成功=false、实际松爪/撤离均未发生，post_retreat_window仍unavailable/stable=null。正常success/failure/all_valid入口全部拒绝该诊断；原始完整性、物理判分与任务标签不改。闭合审计另见 `../collision_clearance_05_02_closed_read_archive.json`，完整H5全读与无损归档均已通过。没有向GPT提供这个人工抬升方案。
