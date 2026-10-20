# V0 demo03 视频场景适配任务

独立模式 `video_demo_adapted`：从完整白色6×6参数化架的指定槽位物理抓取原尺寸器皿，搬运到开盖仪器腔内的A派生适配座，完成支撑交接、对称慢松爪、整手撤离及3秒稳定。原CAD及历史版本保留；本模式不声称原CAD配套或真实校准。

来源架110×110×28mm，净槽16×16mm、深25mm、壁2mm、底3mm、孔距18mm；A1为rack-local −X/−Y角，F6为对角的蓝色邻物。A适配座保持原安装位置及20.4×20.4×29mm外包络，16×16mm贯通配合区、27mm可用深度、2mm底面。只替换原A的视觉与碰撞，B保留。全部尺寸是当前可配置工程假设或原CAD数值，不是实物标定。

```bash
cd /home/wujing/Desktop/vla/LabSim
# GUI；加--headless可无窗口运行。输出必须是尚不存在的新目录。
bash demos/lab_cuvette_demo03/run.sh \
  --output outputs/lab_cuvette_loading/V0_demo03/my_demo

# 同一配置连续5次，顺序占用共用GPU锁。
bash demos/lab_cuvette_demo03/run_fixed.sh \
  outputs/lab_cuvette_loading/V0_demo03/my_fixed5

# 5次固定独立判分全部通过后，10次跨槽+装配平移检查。
bash demos/lab_cuvette_demo03/run_random.sh \
  outputs/lab_cuvette_loading/V0_demo03/my_random10 \
  outputs/lab_cuvette_loading/V0_demo03/my_fixed5/summary/episodes.json

# 已有合格episode的只读过滤和现有MinimalPickDataset训练batch读取。
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.data_check \
  --episode <成功trial目录>/dataset/episode_0000.h5 \
  --score <同一trial目录>/independent_score.json \
  --output outputs/lab_cuvette_loading/V0_demo03/my_dataset_check
```

控制器复用Franka/Lula关节位置目标和demo01释放逻辑；根据实际器皿位置小幅修正对准与下降XY目标。器皿保持20g动态刚体和既有walls28_mm接触模型；运行中不设置器皿位姿、附着、冻结或关闭碰撞。240Hz物理/60Hz控制，每周期明确4步。原生、USD与位姿差分速度均保留；目标底面净支撑力单独记录。

`result.json`是控制器原始结果；`independent_score.json`及`adjudication.json`是实际任务/数据资格；`execution_summary.json`合并显示两层结果。未完成撤离时`post_retreat_window`不可用、稳定结果null，末段仅为`terminal_window`。成功数据独立归入`lab_cuvette_loading_V0_demo03_video_demo_adapted`；native_pair_success和real_calibrated始终false，不阻止适配任务的真实成功样本资格。

复现资产可使用`build_assets.py --output <新的目录>`，不会回写源CAD；场景生成后应先用`preflight.py`核对全架/适配座/三手部的计划，再用`plan_arm.py`核对全臂IK/FK的原始碰撞输入，最后由实际连续运行的原生接触和状态独立判分。采样几何不能冒充全局烹饪几何误差界。
