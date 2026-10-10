# Franka 空烧杯极简抓取 Demo

这个 demo 从空 USD stage 创建地面、灯光、固定桌子、一台 Franka、一个空烧杯和观察相机。使用 Lula 逆运动学计算关节位置目标，通过夹爪接触和摩擦抓取烧杯，再抬起并保持。运行时不打开或引用 `lab_001`，不接入原有任务和训练管线。

## 启动

本机 GUI 启动命令：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/run.sh
```

GUI 默认在结果打印后继续显示并维持最后的机器人关节目标。关闭窗口或按 Ctrl+C 退出。`main` 保留上游原版，开发分支为 `codex/minimal-franka-beaker`。

启动脚本默认使用仓库同层的 `labutopia-env/bin/python`，本机版本为 Isaac Sim 5.1.0.0。其他机器可以通过 `LABSIM_PYTHON=/path/to/isaac/python` 指定已有环境，无需在此 demo 中安装新的 Python 依赖。

自动退出的 GUI 验证和截图：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/run.sh \
  --exit-on-result \
  --save-usd /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_scene.usda \
  --result-json /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_result.json \
  --screenshot /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_success.png
```

无界面运行使用 `--headless --exit-on-result`。将 `--timeout-seconds` 设为 1 可验证超时路径。任务预算按仿真时间计算，不包含 Isaac 启动和初始化；另有墙钟 watchdog，避免 GUI 暂停导致无限等待。

终端最终打印 `SUCCESS`、`FAIL` 或 `TIMEOUT`。退出码分别为 0、1、124；用户中断为 130。详细判据与测量值写入结果 JSON。

## 资产来源

Franka 引用仓库现有 `assets/robots/Franka.usd`，保留其真实关节、碰撞体和固定基座。Franka 包装类和 Lula 逆运动学来自已安装的 Isaac Sim，不调用 LabUtopia 原有机器人包装类附带的相机、传感器和数据管线。

烧杯来自上游提交 `8df72784265c375a327ffa3f0a0cf8c676f229a7` 的 `assets/chemistry_lab/lab_001/lab_001.usd` 中 `/World/beaker2/mesh`。检查发现它嵌在实验室层中，未引用独立 USD，材质绑定指向实验室 `/World/Looks/OmniSurface_Glass`。离线提取其 1698 个顶点、三角面索引，烘焙原始旋转，去除位置偏移后均匀缩放至 X 方向外轮廓 60 mm，实际高度约 72.1 mm，结果保存在 `assets/beaker.usda`。原网格的空腔和杯口保留，没有液体。

**烧杯视觉几何复用了原网格，不是生成的杯状代理模型。** 为方便观察，材质改成不透明蓝色 `UsdPreviewSurface`；碰撞使用 PhysX `convexDecomposition` 近似。质量设为 0.08 kg，开启重力和 CCD，静／动摩擦系数为 1.2／1.0，恢复系数为 0。尺寸、质量和摩擦是本 demo 的设定值，未经过真实烧杯标定；碰撞近似不适合作为液体或精细倾倒验证。

地面、灯光、桌子和相机由脚本生成。桌面高 0.74 m，桌板尺寸 1.2 × 0.8 × 0.08 m；桌子只有固定碰撞体，没有动态刚体。地面使用本地生成的平面和纯色材质，不依赖在线地面纹理。

## 场景和控制

机器人基座固定在 `[-0.30, 0, 0.74]` m，烧杯底部初始放在 `[0.20, 0, 0.741]` m。仿真步长为 1/120 秒，重力为 9.81 m/s²。初始化静置 1 秒后记录实际烧杯初始位置，以免把接触面沉降计入提升高度。

脚本执行靠近 3 秒、下降 2 秒、夹持 1.5 秒、抬起 2.5 秒、保持最多 3 秒。末端目标位置采用固定初始位置，移动阶段使用平滑插值。夹爪最大驱动力为每个手指 40 N，位置目标只施加到机器人关节。烧杯的位姿只在初始化时设定，运行阶段只读取其位置和接触力。

成功需要在保持阶段同时满足：

- 烧杯相对静置后的初始位置升高至少 0.05 m。
- 左右手指与烧杯的接触力分别大于 0.01 N。
- 上述条件连续满足至少 1 秒；任一条件失效，计时清零。

双侧接触要求比仅检查高度更严格，避免将弹飞或自由落体中的器皿算作成功。掉到桌下、被推出工作区、逆运动学不可达或保持阶段结束仍不满足条件时打印失败。超出任务仿真时间预算或墙钟 watchdog 时打印超时。

## 保存 USD

默认生成 `outputs/minimal_pick/scene.usda` 和 `outputs/minimal_pick/result.json`，可通过参数改路径。USD 是初始化静置后的场景，保存时间在任务动作开始之前。`Flatten` 把机器人和烧杯的 USD 引用展开，保存文件不包含完整实验室或对实验室的引用。渲染仍需 Isaac Sim 自带的 shader 实现。

在 Isaac Sim 中打开该 USD 可以检查场景和碰撞；USD 本身不包含 Python 任务状态机，重新执行抓取仍使用启动脚本。输出目录由项目现有 `.gitignore` 忽略，运行截图和 23 MB 左右的完整场景不提交到 Git。

## 实际验证

2026 年 10 月 10 日，本机 Isaac Sim 5.1.0.0、RTX 4090 上已运行初版：无界面物理抓取成功，最终升高约 0.1189 m；GUI 物理抓取成功，最终升高约 0.1193 m，双侧接触连续保持 1 秒，并保存了可查看的 GUI 截图和初始化场景 USD。

最终版本 GUI 复测成功，最终提升高度约 0.1192 m，连续双侧接触保持 1 秒，退出码为 0；纯色地面与成功截图已实际检查。1 秒任务预算的运行正确打印 `TIMEOUT` 并返回退出码 124。强制夹爪保持打开的物理负对照最终提升约 0 m、没有双侧接触，正确打印 `FAIL` 并返回退出码 1。导出 USD 重新加载后运行 120 个物理步，烧杯仍稳定在 0.74 m 桌面高度；场景不含任何外部 USD 引用，桌子固定碰撞、烧杯质量和场景重力检查通过。语法检查和 Shell 语法检查通过。

未验证其他机器／Isaac 版本、真实烧杯参数、液体行为、随机初始位置或统计成功率。

项目背景、完整规划书归档与本次工程范围见 [背景说明](../../docs/background/README.md)。
