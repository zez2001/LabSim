# V0_demo01 连续工程演示

这是独立的新版本，复用 ext02 的 `walls28_mm` 器皿碰撞、Franka/Lula 与既有采集写入接口。原生配套关口保持，新增工装明确为工程设计，保留原仪器全部部件及原尺寸。见 [执行约定](../../docs/lab_cuvette_loading/V0_demo01/implementation_contract.md)。

所有输出目录必须不存在；共享 GPU 锁顺序执行。去掉 `--headless` 可显示 GUI。

```bash
cd /home/wujing/Desktop/vla/LabSim
bash demos/lab_cuvette_demo01/run.sh --headless \
  --config config/lab_cuvette_loading/V0_demo01/engineering_demo.yaml \
  --output outputs/lab_cuvette_loading/V0_demo01/my_workflow_01
../labutopia-env/bin/python -m demos.lab_cuvette_demo01.analyze \
  outputs/lab_cuvette_loading/V0_demo01/my_workflow_01/trial_00
```

`demo_release.yaml` 为桌面诊断，`native_pair.yaml` 为不启动物理的原生身份/几何阻断记录。工程完整流程保存 `workflow_success`；原任务 `full_success` 和 `full_task_eligible` 始终 false，不进入原成功训练索引。最终以 `independent_score.json` 和实际录像复核。

每次保存配置、代码/资产 SHA、初态、逐物理步状态及双指法向/切向力、原生接触事件、阶段、obs/action/next 对齐 H5、1920×1080 连续主录像和近景。实际有效后端 CPU PhysX TGS，240 Hz物理/60 Hz控制，4子步，原摩擦及增益不变。局部速度与几何局限随结果保留。

初步开发记录（尚未作为固定五次验收）：桌面第二条确实释放、撤离并稳定，但早期落体穿透和开爪前支撑窗口未通过独立复核。完整第一条执行全部阶段，但旧斜向接近擦碰原仪器前角；独立判分失败。当前修正为来源正上方竖直接近、无重复初始化传送、连续承重确认；其验证结果将另存，不覆盖上述失败。

首条独立通过记录：`outputs/lab_cuvette_loading/V0_demo01/workflow_dev02/trial_00`，执行提交 `bf90910`，54.9667秒仿真，全部阶段已执行；最大源几何穿透0.014365mm，撤离净空86.128mm，原生配对未执行。五次固定检查使用相同物理/控制，仅扩大主录像取景，完成后汇总全部结果。

五次顺序复现：`bash demos/lab_cuvette_demo01/run_fixed.sh outputs/lab_cuvette_loading/V0_demo01/my_fixed_five`。独立通过后的小范围布局命令加 `--random-layout --seed 7000`；来源及目标工装XY各±1mm，不改变原资产尺寸或物理参数，每条先执行几何净空审查。

固定五次已完成并独立通过：`outputs/lab_cuvette_loading/V0_demo01/fixed5_20261019/fixed_0` 至 `fixed_4`。小范围随机检查入口会先核对这五条独立结果：

```bash
bash demos/lab_cuvette_demo01/run_random.sh \
  outputs/lab_cuvette_loading/V0_demo01/fixed5_20261019 \
  outputs/lab_cuvette_loading/V0_demo01/my_random_three
```
