# Project_v1_1 腕部相机只读诊断

目前证据支持先调整固定光轴，再比较图像清晰度。Project_v1 的腕相机安装在手坐标 `[0.075, 0, 0] m`，光轴却瞄向 `[0, 0, 0.35] m`；已声明的机器人TCP在手前100 mm。用每次实际公开的TCP及相机标定投影，18次模型观察中的TCP都在约 `(255.90, 56.58)` px，即384高画面的14.7%处。手前75 mm的轴上点约为y=2 px。实际闭爪及离架JPEG确实把器皿上部/手爪推到画面顶端，大部分画面留给桌面。

这是固定光轴与近指端区域不匹配的直接证据；没有发现provider裁剪造成此问题。仍不能仅凭投影排除遮挡或证明候选相机已可用。

## 已读取的实际输入与边界

来源为正式第4次 `attempt_0003`，执行提交 `7a7cbb81c6fcede84b48d1e9b60f66c68dfac0f0`。已核对18份实际public observation及36张发送JPEG：文件SHA与对应manifest、`model_image_transforms`一致；原生640×480，经Pillow LANCZOS等比例缩为512×384，JPEG quality60、detail=low，crop=null、旋转0。像素中心变换为 `u'=.8(u+.5)-.5`、`v'=.8(v+.5)-.5`。

采集器的256×256策略图片是另一条数据通路，不能把它当作GPT实际输入；本次GPT网络输入保留4:3比例。上游provider如何内部处理low图片未知。

实际到达的图像：

- 初始：decision0，0.0167 s。完整来源架/仪器关系可见，腕部画面主体仍为桌面。
- 接近：decision4/7/12，8.0167/14.0167/21.4167 s。架和指端持续挤在上方。
- 闭爪：decision13，23.4167 s。公开双指接触读数约1.6 N，器皿/手爪上部被截断；独立持续双指接触事件稍后才在23.5458 s成立。
- 抬升/离架：decision14，25.4167 s。独立离架事件25.1375 s；物体仍处上方，不能据此写稳定抓持成功。
- decision15/16，27.4167/29.4167 s：公开接触已为零；有继续上抬/横移动作，没有有效持物搬运样本。
- 预插入、插入/承托、开爪及退让没有执行，相应实际GPT输入必须标为 unavailable。teacher旧录像只能作独立传感器诊断参考，不能补成这个GPT的阶段输入。

闭爪实图：[decision13腕视](../Project_v1/evaluation/gpt_formal5_01/attempt_0003/episode_0000/gpt_control/observations/decision_000013/wrist_camera.jpg)。离架后实图：[decision14腕视](../Project_v1/evaluation/gpt_formal5_01/attempt_0003/episode_0000/gpt_control/observations/decision_000014/wrist_camera.jpg)。完整输入和SHA索引见同目录JSON。侧部全景保留了布局，但手臂遮挡和像素不足明显；在公开TCP深度处，理想正对相机的10 mm横向跨度只有约4.0–4.4 px，不适合作唯一接触视角。

## 建议的固定安装候选，不是已验证配置

在新版本配置中优先只改光轴目标，保留镜头、实际安装位置和上方向。相机始终继承同一个panda_hand，不逐帧追踪对象或随任务阶段切换朝向。

```yaml
cameras:
  wrist_camera:
    parent_link: /World/Franka/panda_hand
    prim_path: /World/Franka/panda_hand/WristCameraV11
    localeye_m: [0.075, 0, 0]
    localtarget_m: [0, 0, 0.10]
    localup: [0, 0, -1]
    focal_length_cm: 1.2
    horizontal_aperture_mm: 20.955
    resolution: [640, 480]
    fps: 60
    policy_resolution: [256, 256]
```

`look_at_usd`对此固定配置给出的wxyz四元数约 `[-0.223606798, 0.670820393, -0.670820393, 0.223606798]`，手坐标光学前向 `[-0.6,0,0.8]`。正负等价四元数均可。相对原光轴约转24.78°；水平/垂直FOV仍约82.25°/66.44°。标定K仍来自实际传感器读取，不能把这些名义光学参数当真实相机校准。

同一固定机器人轴上75/100/150 mm点，旧配置在512×384模型图中的y约2.18/56.58/116.24 px；候选为150.01/191.90/245.21 px。这是CPU针孔投影，不是新渲染图、器皿真值框或遮挡证明。选100 mm来自已知机器人TCP几何，不依赖器皿真值。

先实渲染这一个候选，检查初态的来源架是否仍可观察、指端与器皿是否被手体遮挡、腔口/座口是否被盖板遮挡。若仍有经过验证的边缘裁切，再单因素将焦长降为1.0、保留孔径，FOV约92.67°/76.32°；扩大FOV会减少物体像素，不能代替正确瞄准。不要一开始同时改安装位置、FOV、分辨率及provider设置。

## 固定规则局部图与更清晰配置

局部图仅作可选补充。候选固定原生ROI为 `[x0=160,y0=80,w=320,h=320]`，所有观察使用同一像素规则，输出320×320且不上采样，不能从物体位置、评分器、任务阶段或真值框选ROI。`K_ROI=T_crop @ K_native`，其中 `T_crop=[[1,0,-160],[0,1,-80],[0,0,1]]`。全景和完整腕视继续保留；图上不能添加真值标记给模型。

当前serializer和观察保存函数固定为两路RGB/5个content块，第三张局部图需要显式版本化wire格式、通道标识、ROI与K、字节SHA及读取回归，不能临时追加一张未追溯的图片。先完成主视野改进，局部图默认不启用。

视野通过后，再小规模比较原512×384/quality60/low与原生640×480、max_side_px640、quality80、detail=high。原生不变时没有额外传感器像素，改善的是传输保真及provider细节设置。先用相同冻结诊断帧做人工可见性对比，再以严格小预算记录模型识别错误、实际JPEG字节、usage、推理延迟和ledger增量。不预先宣称识别或费用改善。

## 阶段输入验收建议

这些是待实施的相机QA目标，不改变物理判分：reset、接近、闭爪、抬升离架、稳定持物搬运、预插入、插入/承托、开爪、退让各存一对实际输入及manifest。每阶段保留observation ID、logical/engine/render时间、安装/世界位姿、K_native/K_transmitted、resize/crop/像素变换、JPEG SHA及公开的开口/接触反馈。

先用明确标注的确定性或teacher传感器诊断路线覆盖未来操作姿态，检验固定相机；它不构成GPT运行。再保存真实GPT实际到达阶段的发送图，未到阶段保持 unavailable。

逐图人工检查双指末端、器皿可见段和当前架口/座口能否分辨，是否有持续遮挡；建议接触相关轮廓在512×384图中留至少8 px边缘余量，近指端操作时公开机器人TCP处于中央40%×40%范围。不能只凭投影判断“可见”。释放时应同时看到独立器皿与已分开的手指，退让后能看到目标承托区域。侧视继续覆盖来源架、机器人和单台仪器；若腕视未覆盖后续腔内过程，需要再调整固定安装或声明另一种固定视角，不能隐式追踪物体。

## 源码位置与执行状态

`config/lab_cuvette_loading/Project_v1/standard.yaml` 的 `cameras` 段定义原安装。`demos/lab_cuvette_env_v1/cameras.py:22 look_at_usd`、`:410 create_cameras`、`:227 CameraRig.get_meta` 定义USD -Z光学前向、固定父子变换、实际K及256策略图变换。`policy/backends/cubence_tools.py:319 observation_content`、`:358 save_observation_artifacts` 定义实际模型JPEG与发送原件保存，配置在 `config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json:images`。JSON记录了源码在正式提交与当前读取时的SHA对照。

本审查只读代码、配置及已关闭的输入文件，并做CPU投影；没有改任何相机/代码配置、运行GPU、调用模型或验证候选新视野。旧Project_v1记录保持原样。
