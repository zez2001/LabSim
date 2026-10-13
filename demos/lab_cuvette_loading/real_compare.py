"""Separate static state visualization from simulated command-response diagnosis."""
import argparse,sys,json,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def main():
 p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--mode',choices=['static_geometry','command_response'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0.yaml');p.add_argument('--headless',action='store_true');args=p.parse_args()
 from demos.lab_cuvette_loading.real_import import normalize_record
 raw=json.loads(args.record.read_text());record=normalize_record(raw);t=np.array(record['timestamps_s']);q=np.array(record['joint_states_SI']);a=np.array(record['commands_SI'])
 from isaacsim import SimulationApp
 app=SimulationApp({'headless':args.headless});code=1
 try:
  from omegaconf import OmegaConf
  from demos.lab_cuvette_loading.model import export_assets,sample_layout
  from tasks.lab_cuvette_loading_task import LabCuvetteLoadingTask
  from isaacsim.core.utils.types import ArticulationAction
  args.output.mkdir(parents=True,exist_ok=False);cfg=OmegaConf.load(args.config);assets=args.output/'assets';manifest=export_assets(assets,cfg);task=LabCuvetteLoadingTask(cfg,sample_layout(cfg,'standard',0),assets,manifest);task.initialize();results=[]
  if args.mode=='command_response' and len(t)<2:raise ValueError('response mode requires a successor state')
  for i in range(len(t) if args.mode=='static_geometry' else len(t)-1):
   if args.mode=='static_geometry':
    # Only robot state is placed for static geometry QA; no physical task claim.
    task.robot.set_joint_positions(q[i]);task.world.render();task.save_views(args.output,f'frame_{i:04d}')
   else:
    if i==0:task.robot.set_joint_positions(q[0]);task.robot.set_joint_velocities(np.zeros(9))
    task.robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=a[i]))
    dt=t[i+1]-t[i];steps=round(dt*cfg.physics.hz)
    if abs(steps/cfg.physics.hz-dt)>1e-6:raise ValueError('record timestamps must align with physics grid; resample explicitly first')
    for _ in range(steps):task.world.step(render=False)
    task.world.render()
   actual=task.robot.get_joint_positions();successor=i if args.mode=='static_geometry' else i+1
   results.append(dict(command_time_s=float(t[i]),response_time_s=float(t[successor]),reference_state_SI=q[successor].tolist(),command_SI=a[i].tolist(),simulated_state_SI=actual.tolist(),max_arm_error_rad=float(np.max(abs(actual[:7]-q[successor,:7])))))
  (args.output/'comparison.json').write_text(json.dumps(dict(mode=args.mode,purpose=record['purpose'],synthetic_fixture=raw.get('synthetic_fixture',False),task_success_not_scored=True,comparison=results),indent=2));task.close();code=0
 except BaseException:traceback.print_exc();raise
 finally:
  from omni.kit.app import get_app
  get_app().post_quit(code);app.close()
if __name__=='__main__':main()
