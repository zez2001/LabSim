# c793 双层夹持保持机制只读复核

复核固定执行提交 `c793a12b8f097eb47a9158a708d896993a05116c`。仅用 `git show` 读取该提交源码，不以当前工作树替代真实运行版本；未读取raw/H5或活跃输出，未运行API/GPU，未修改控制、配置、评分或报告draft。各源SHA与带原行号片段在 `review.json`。

结论：此版本提供“首次接触冻结、不意外回张、失触后向原逻辑目标慢闭”，没有在持续双侧接触时闭环恢复摩擦承重裕量。teacher与generic都冻结于同一开口时，teacher给出的逻辑下界还可能阻止generic进一步闭合。这是源码可确认的机制限制，不能单凭它证明某次物理失败的全部因果。

## teacher 的作用范围

新版teacher `act` 第84–107行的slow_zone同时要求仍处于GRASP、此前未锁存、双侧接触尚不成立。它只限制近接触闭合速度；锁存后或两侧均超过检测阈值时，不是法向力调节器。

父teacher `act` 第213–244行在首次双侧接触时，依据测得指距与重量/摩擦/刚度估计生成一次冻结目标。`_latch` 第134–139行在配置`preserve_first_contact_command`下保留同一目标，第186行及244行随后持续使用`latch_opening`。该逻辑避免确认窗口中继续快闭和锁存时回张，但没有把后续接触力与承重所需力比较。第188–196行的相对位移与双侧低接触停止监测也不是抓持力伺服。

## generic helper 的实际分支

`GenericContactHold.update` 第87行把两侧读数各自大于阈值视为bilateral。第88–89行确实每tick重算重量估计候选，但第99–113行只在首次、没有frozen时应用它；已有frozen且bilateral时，直接`hold_contact_target`并保持原值，没有重新采用候选、力误差或摩擦裕量反馈。

即使两侧读数都大于0.03N，只要这一二值接触成立，helper不会因其低于重量所需裕量而补闭。代码采用的工程估计为`mu=sqrt(0.5×0.8)`、质量20g、安全系数2，在对称法向简化下每指约需0.3102N；0.03N是接触检测门槛，不是承重门槛。此公式未校准真实法向、摩擦、压力中心或驱动刚度，不能当作实测保持力保证。

失去任一侧检测后才进入第114–123行慢闭恢复：

`applied = min(previous, max(logical, previous - speed × dt))`

因此，若`logical = previous = frozen`，代数上`applied`严格等于`previous`，没有再闭合空间。若previous大于logical，则可按速率向logical靠近，仍不能越过该下界。已有持续双侧接触时本来就不会进入恢复分支。

## 双层目标如何传递

固定提交`run.py`第123–128行直接执行`teacher.act(...) → env.step(action)`。teacher返回第381–383行带显式夹爪开口与力上限，没有另存一个更小的最终闭合逻辑目标。

新版task `_convert_action`第127–130行优先取`raw_model_action.gripper_opening_m`，不存在时取本次opening，因此直接teacher动作的generic logical就是teacher已冻结开口。第135行设置兼容策略锁存；父任务`step`第241行的旧策略二次锁存对含teacher_phase的动作跳过，不会另行提供承重裕量恢复。

这解释了当两层都已冻结同值时，helper既不会在正接触中主动增加承重裕量，也可能在失触后被同一logical界限卡住。真实运行何时接触、是否不足、杯如何运动以及具体失败时刻，须与独立关闭物理审计交叉核对；本文件没有读取或改写那些数据。

## 证据定位

- `controllers/lab_cuvette_project_v1_1_controller.py`：teacher v3近接触速度限制，84–107行。
- `controllers/lab_cuvette_env_v1_controller.py`：首次冻结213–244行；锁存策略125–149行；持续目标186行；直接动作377–388行。
- `demos/lab_cuvette_project_v1_1/gripper_hold.py`：候选87–89行；冻结99–113行；失触恢复114–123行。
- `tasks/lab_cuvette_loading_project_v1_1.py`：逻辑开口传递127–135行。
- `tasks/lab_cuvette_loading_env_v1.py`：实际施加及旧策略跳过230–256行。
- `demos/lab_cuvette_project_v1_1/run.py`：teacher直接调用123–128行。

所有行号均指c793固定提交，当前工作树若新增方法后行号移动，不影响此审计。没有实施改进或调整任何阈值；也不能由源码机制推导一条新的成功轨迹。
