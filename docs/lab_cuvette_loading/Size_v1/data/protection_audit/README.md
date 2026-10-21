# Size_v1 原座保护与尺寸系列核查

以 Env_v1 交付提交 `c61c5bd` 和该版本实际 `preinsert_continuous_latch_01` 的绑定为基准。本核查只读取文件和离线 USD，没有启动 Isaac 进程、GPU 或物理步，没有改动资产、配置、冻结清单和原始结果。

## 原座和装配保持的证据

原仪器的全部 3 个实际 USD 引用层均同时符合旧 Git LFS 内容哈希和旧 Env_v1 运行绑定哈希：

- V0_demo04/instrument_native.usda：`b7145d71ca9668630466648a6144c26de9d555ca228259e22ecb3bf4e02a3a4e`。
- V0_demo02/video_pose_verified/instrument_native.usda：`2c075c4e4273ce23fcc0843e56ed0b42c66c030aeb9cf6fc1fbed89da4bd8c77`。
- V0_ext01/source/newnew4.usd：`8261714be7250b61466e9b3537a25438a5cc441c20a465ea6b3c27b43383a1dc`。

因此两个座、机身、盖板、源网格、单位、累计变换及 authored 碰撞/材质属性均保留原层内容。选定座始终为 A `candidate_far_hinge`，碰撞 prim 为 `/Asset/Collision/SourceMesh3`：启用、静态、`approximation=none`，接触偏移约 0.00005 m、rest offset 0。绑定物理材质静摩擦约 0.6、动摩擦 0.5、恢复系数 0，组合方式 average。详见独立 composed USD 快照。

实际 10.00 mm 和 10.50 mm 运行保存的 `physics`、`adapter`、仪器来源、装配目录、世界位置和朝向、来源架参数，与 Env_v1 基准逐项相同；各自实际几何绑定中的上述依赖哈希也相同。完整 `physics` 字典相等，包括 CPU 基线使用的 240 Hz 物理、60 Hz 控制、TGS、迭代、摩擦、恢复及偏移参数。

新增 `[+0.650,+0.001,0] mm` 是器皿**控制装载轴相对原座的偏移**，不是移动内部座或修改座的尺寸。实际已附着 PhysX shape 的完整烹饪顶点没有跨历史版本全部读取，不能由本次文件核查宣称该层全局误差为零。

## 全部尺寸资产核查

35 个独立资产与注册项全部重新检查通过。原 12.5 mm 控制源哈希仍为 `8d52757227303edd4f38918ee04763481f08846fdd8daa6803295c8fc77c689d`。

每个资产均满足：

- 一个视觉网格及 28 块碰撞输入均采用同一个 `diag(w/12.5,w/12.5,1)` 变换，Z 顶点完全不变；底部原点、拓扑、其余 mesh 属性及全部材质和 shader 属性保持。
- 源文件不变，实际 USD 哈希与注册项一致，独立 JSON 与 registry 一致；米制、Z-up、defaultPrim 和独立加载约定保持。
- 同一 20 g 假设重新积分闭合视觉材料体，COM 和完整惯量与重载 USD 一致；材料体积符合 XY 面积比例。数值密度随宽度改变，没有同时保持材料密度的假设。

最大观察到的仿射点写入舍入差约 `2.3804e-10 m`，只用于数值文件一致性检查，不是物理或实物精度。逐资产结果见 `all35_asset_checks.csv`。

## 推荐范围的准确措辞

几何搜索覆盖 9.50 至 12.50 mm，统一检查四个直立方位及各自全部有界 XY 平移域。

- **10.70 mm 是已采样尺寸中保守连续全深竖直扫掠正证书的最大值**，不是连续物理成功范围的上限。
- **10.72 至 11.00 mm 的完整路径仍未认证，属于未知**；不能写成绝对不能插入。
- 已观察 11.00 mm 的入口必要域仍存在；11.02 mm 及以上已测试尺寸在这四个直立方位的入口必要域为空。没有对任意倾斜 6DoF 路线作全局判定。
- 初始推荐 10.00 mm 使用固定原座偏移，保守侧向输入表面余量约 0.350 mm；几何余量不等同于控制精度或真实配合尺寸。

当前物理证据仅支持以下离散结果，**不能据此宣称 9.5 至 10.7 mm 的连续物理范围都能成功**：

| 实际运行 | 尺寸 | 仿真时长 | 独立完整任务结果 | 解释 |
| --- | --- | --- | --- | --- |
| loading_01 | 10.00 mm | 105.8167 s | SUCCESS | 实际提取、搬运、装载、松爪、撤离及之后 3 s 稳定均通过。仍保留原生与差分线速度不一致及 native cooked 全局重叠未知告警。 |
| loading_1050_01 | 10.50 mm | 105.7833 s | GRASP_SLIP | 独立抓持和 loading_sequence 门控失败。杯底原点相对手的最大漂移约 0.6160 mm，大于原 0.2 mm 门槛；配置抓取锚点漂移约 0.1272 mm，两个定义不能混用。该次仍实际释放、撤离且终态稳定，不能说它已证明几何插入受阻。 |

两个开发运行使用不同器皿资产；10.50 mm 的失败不能填入最终冻结 10.00 mm standard 场景的失败配额。正式 5 次验证当前另行运行，须等待闭合记录和数据资格审计，不能把正在执行的 episode 预写为成功。

## 历史保护与局限

`legacy_namespace_check.json` 列出核查的历史 V0/ext/demo 命名空间和所有 tracked 路径，未发现相对 Env_v1 基准的改动。旧 Env_v1 交付清单内 84 个小型 JSON/YAML/CSV 证据的哈希均一致。local main 仍为原提交，详见 JSON。

没有对所有忽略的大体积旧 HDF5 和视频做完整的前后哈希，因此不宣称全部历史大输出已逐字节核对。没有真实质量、材料或机器人动力学校准；本轮结论限定于当前资产、控制和物理配置。

## 报告数据联结注意事项

1. 最终报告前重新生成 `summarize_lab_cuvette_size_v1.py` 输出，并传同一份 `collection_audit`，保留真实 5 次结果和 20+20 资格；审计前未知数不得补值。
2. `--verification-run-prefix verify5_` 现按路径组件识别正式嵌套目录，不把 sibling success 或 controlled_failure 批次计入 5 次验证。
3. 当前主录像若使用 `loading_01`，报告显式指定 `--primary-episode-id fa9fda66-2cff-488f-81b9-416569928d78`。更换为冻结场景正式成功录像时，相应改为该录像的真实 episode UUID。
4. 生成器读取 `config_snapshot` 与其 SHA；冻结清单、collection audit 和视频 manifest 必须实际存在且相互对应。DOCX 尚未在本核查中生成。

文件：`protection_audit.json`、`original_A_seat_composed_USD_snapshot.json`、`all35_asset_checks.csv`、`legacy_namespace_check.json`、本说明和一次性离线核查脚本 `audit.py`。脚本使用新目录输出并拒绝覆盖已有证据。
