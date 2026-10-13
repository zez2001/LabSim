"""Final evidence summary and scientific plots from recorded outcomes only."""
import argparse,json,csv,sys,os
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def main():
 p=argparse.ArgumentParser();p.add_argument('--root-output',type=Path,default=ROOT/'outputs/lab_cuvette_loading');p.add_argument('--output',type=Path,default=ROOT/'docs/lab_cuvette_loading/results_V0');args=p.parse_args();root=args.root_output;out=args.output;out.mkdir(parents=True,exist_ok=True)
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from PIL import Image
 groups=['standard10_verified_V0','appearance_check_V0','layout_check_V0','random_test_V0','collection_V0','standard_replay_V0','random_replay_V0'];rows=[];summary={};links={}
 for name in groups:
  path=root/name/'summary.json'
  if not path.exists():summary[name]=dict(not_run=True);continue
  records=json.loads(path.read_text());counts={s:sum(r['status']==s for r in records) for s in sorted(set(r['status'] for r in records))};summary[name]=dict(attempts=len(records),successes=sum(r['full_success'] for r in records),statuses=counts,simulation_seconds=sum(r.get('simulation_seconds',0) for r in records),episode_wall_seconds=sum(r.get('wall_clock_seconds',0) for r in records),max_overlap_mm=max(r.get('max_overlap_mm',0) for r in records),gpu_memory_MiB=[r.get('gpu_memory_MiB') for r in records])
  for i,r in enumerate(records):
   initial=root/name/f'episode_{i:04d}_initial.json';sample=json.loads(initial.read_text()) if initial.exists() else {};layout=sample.get('layout',{});rows.append(dict(group=name,episode=i,seed=r['seed'],status=r['status'],reason=r['reason'],full_success=r['full_success'],source_slot=r.get('source_slot_id'),rack_x_m=layout.get('rack_xy_m',[None,None])[0],rack_y_m=layout.get('rack_xy_m',[None,None])[1],rack_yaw_deg=layout.get('rack_yaw_deg'),instrument_x_m=layout.get('instrument_xy_m',[None,None])[0],instrument_y_m=layout.get('instrument_xy_m',[None,None])[1],instrument_yaw_deg=layout.get('instrument_yaw_deg'),actual_source_x_m=sample.get('objects',{}).get('target',{}).get('position',[None,None])[0],actual_source_y_m=sample.get('objects',{}).get('target',{}).get('position',[None,None])[1],max_depth_mm=r.get('max_depth_mm'),max_overlap_mm=r.get('max_overlap_mm'),sim_s=r.get('simulation_seconds'),wall_s=r.get('wall_clock_seconds'),video=str(root/name/'video'/f'episode_{i:04d}.mp4')))
  successes=[i for i,r in enumerate(records) if r['full_success']]
  if successes:links[name]=[str(root/name/'video'/f'episode_{i:04d}.mp4') for i in [successes[0],successes[-1]]]
 (out/'summary.json').write_text(json.dumps(summary,indent=2));(out/'representative_videos.json').write_text(json.dumps(links,indent=2))
 if rows:
  with (out/'episodes.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 # Actual source vessel and target layout; success/failure labels come from independent scorer.
 fig,axs=plt.subplots(1,2,figsize=(10,4))
 for ax,name in zip(axs,['random_test_V0','collection_V0']):
  selected=[r for r in rows if r['group']==name]
  for r in selected:
   if r['actual_source_x_m'] is None:continue
   ax.scatter(r['actual_source_x_m']*1000,r['actual_source_y_m']*1000,c='tab:green' if r['full_success'] else 'tab:red',s=25)
   ax.text(r['actual_source_x_m']*1000,r['actual_source_y_m']*1000,str(r['seed']),fontsize=6)
  ax.set(title=name,xlabel='actual initial vessel x (mm)',ylabel='actual initial vessel y (mm)');ax.grid(alpha=.2);ax.margins(.12)
 fig.tight_layout();fig.savefig(out/'random_actual_layouts.png',dpi=160);plt.close(fig)
 fig,axs=plt.subplots(1,2,figsize=(10,4))
 for ax,key,label in zip(axs,['max_depth_mm','max_overlap_mm'],['maximum actual target-neighborhood depth (mm)','maximum geometric overlap (mm)']):
  for name,c in [('standard10_verified_V0','tab:blue'),('random_test_V0','tab:green'),('collection_V0','tab:orange')]:
   values=[r[key] for r in rows if r['group']==name and r[key] is not None];ax.plot(range(len(values)),values,'o-',label=name,color=c)
  ax.set(xlabel='episode index within group',ylabel=label);ax.grid(alpha=.2);ax.legend(fontsize=6)
 axs[0].set_ylim(0,22);axs[0].axhline(18,color='gray',ls='--');axs[1].set_ylim(0,.28);axs[1].axhline(.25,color='red',ls='--',label='V0 tolerance');fig.tight_layout();fig.savefig(out/'depth_overlap.png',dpi=160);plt.close(fig)
 # Side-by-side visual relation comparison, with explicit proxy caption.
 real=root/'media_review_20261013/frame_00.jpg';sim=root/'standard_demo_V0/episode_0000_initial_camera_1_rgb.png'
 if real.exists() and sim.exists():
  fig,axs=plt.subplots(1,2,figsize=(10,4));im=Image.open(real);axs[0].imshow(im.crop((0,0,im.width//2,im.height)));axs[0].set_title('Provided video: external view');axs[1].imshow(Image.open(sim));axs[1].set_title('V0 scene: Franka + synthetic instrument proxies')
  for ax in axs:ax.axis('off')
  fig.tight_layout();fig.savefig(out/'scene_comparison.png',dpi=160);plt.close(fig)
 # Count physical disk use once per inode: aggregation hard links are not extra episodes/storage.
 seen=set();total=0
 for p in root.rglob('*'):
  if p.is_file():
   s=p.stat();key=(s.st_dev,s.st_ino)
   if key not in seen:seen.add(key);total+=s.st_size
 (out/'storage.json').write_text(json.dumps(dict(unique_inode_bytes=total,GiB=total/2**30,scope=str(root)),indent=2))
 audit=root/'all_audit_V0.json';lines=['# LabSim 器皿装载 V0 实验报告','',f'代码分支 codex/lab-cuvette-loading；物理控制/判分实现独立于 minimal_pick 和 minimal_precision_insertion。数据目录：{root}。','', '## 已运行结果','']
 for name,v in summary.items():
  lines.append(f"- {name}: 尚未运行。" if v.get('not_run') else f"- {name}: {v['successes']}/{v['attempts']} 完整成功；分类 {v['statuses']}；模拟时间合计 {v['simulation_seconds']:.2f}s；episode 墙钟合计 {v['episode_wall_seconds']:.2f}s（不含子进程启动/汇总）；最大静态几何重叠 {v['max_overlap_mm']:.6f}mm。")
 lines+=['','## 证据与判分','', '从来源架中的动态透明方形器皿开始，实际双指接触夹取、提取、搬运、进入仪器内装载座、张开撤离并独立稳定至少1秒。控制只下发机器人关节目标；没有运行中设置器皿位姿、运动学器皿或夹爪绑定。成功要求实际装载深度≥18mm、朝向误差≤5°、释放/撤离、稳定漂移≤0.3mm及全程静态实体重叠≤0.25mm。标准/随机条件使用相同判据。最大深度限定于目标邻域；脚本阶段不能代替实际成功。','', 'USD 新进程独立加载、两次复位、原生 Cube 尺寸和空目标孔的 PhysX 底面射线检查保存于 usd_reload_check.json。穿透检查对器皿五个壁/底与静态碰撞 Box 做实际姿态的15轴 SAT；没有声称读取全部 cooked shape，也未完整覆盖机器人网格/动态干扰器皿的全部重叠。','', f"全量数据审计：{'已生成，详情见 '+str(audit) if audit.exists() else '尚未完成，不能认定全量验证通过。'}。实际9维关节状态，8维对称夹爪动作；RGB CHW uint8、256×256、60Hz控制周期采集。obs/action/next_state、终止标记、有限状态、RGB和episode边界均由审计检查；ACT/DP只读取batch，没有训练或策略成功证据。",'', '物理回放使用该条轨迹的实际初态和采样布局，执行记录的机器人绝对关节动作，不回放器皿位姿。显式位姿/速度恢复不包含隐藏的PhysX求解缓存；回放是否成功以上面的独立结果为准。','', '## 场景重现与限制','', '逐段查看143帧/2.4fps/59.584s双视角视频及实际提供的4张照片，提取13个关键时刻。复现白色来源架、蓝色工作区、开盖白色仪器/黑色腔、腔内座、近邻结构、绿幕和双视角。未确认真实“neo”机器人型号，采用既有Franka代理；面板、背景和邻近已装器皿作简化。器皿13×13×45mm、20g、装载内宽15mm/深20mm均为合成原型值；图像只提供关系参考，不提供尺寸标定。','', '采用PhysX CPU/TGS，240Hz物理/60Hz控制、4子步，有限87/12N·m手臂力矩和8N夹爪力；SI运行时增益/速度/力上限已读回。contact/rest offset为0.1/0mm，摩擦/求解配置固定；没有混入物理参数随机化或重做亚毫米扫描。接触冲量按当前physics_dt换算力。','', '随机范围：架体XY±10mm/yaw±3°，仪器XY±5mm/yaw±2°，合法前排槽位及槽内±0.25mm、光照0.8–1.2及材质色。A外观、B布局独立检查；测试2000–2019与采集3000–3019预先冻结且分开。初始化几何/稳定性不合法记录失败，不按专家成败替换seed。本轮不拓展后排密集抓取。','', '固定标准重复只能说明当前canonical初态的运行重复性。随机20条件与20采集尝试只能说明声明范围下的原型结果，不是广泛真实场景成功概率。全部成功也不构成真实仪器/真实机器人精度或real-to-sim gap结论。','', '## 工程问题与后续真实数据','', '同一Isaac进程多次换空Stage出现旧相机渲染节点错误，改用每episode新进程并顺序汇总；批次路径硬链接兼容性问题也已修复。开发/基础设施调试输出全部保留，清单development_attempt_inventory.json；其成功/未完成记录不混入正式验收批次，也不作学习数据。没有隐去物理失败或放宽阈值。','', '当前没有真实校准数据。导入接口区分静态关节状态画面检查和命令响应仿真，检查单位/坐标/关节名/动作语义，拒绝跨机器人绝对关节回放。接口合成夹具只验证功能；参数导入创建新V1及历史，不覆盖V0，最终验证数据禁止调参。后续先确定真实机器人/工具，再测尺寸/质量/布局/相机并替换估计参数；重新验收standard/random/判分/旧回放后，以独立真实验证数据判断模型差距。','', '自定义LabSim任务借鉴RoboDojo配置/seed/汇总理念；不属于RoboDojo官方评测。不操作真机，不模拟光谱/液体/化学结果，不开展ACT、Diffusion或VLA训练。','', '## 交付索引','', f'- 运行命令：[README]({ROOT}/demos/lab_cuvette_loading/README.md)。',f'- 规格/来源/假设：[task_spec]({ROOT}/docs/lab_cuvette_loading/task_spec.md)，参数来源清单位于config/lab_cuvette_loading。',f'- 真实接口：[real_data_interface]({ROOT}/docs/lab_cuvette_loading/real_data_interface.md)。',f'- 全部episode记录：[CSV]({out}/episodes.csv)；代表视频索引：[JSON]({out}/representative_videos.json)。',f'- 唯一inode输出体积 {total/2**30:.3f} GiB（含保留调试输出和成功合并HDF5；硬链接不重复计）。显存为各episode结束时nvidia-smi整卡样本，包含其他桌面进程，非严格峰值或独占性能测量。','',f'![场景关系对照]({out}/scene_comparison.png)',f'![实际采样布局]({out}/random_actual_layouts.png)',f'![目标深度与几何重叠]({out}/depth_overlap.png)']
 (out/'report.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
