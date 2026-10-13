"""New-process USD load, PhysX hollow-slot rays and actual reset check."""
import argparse,sys,json,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def main():
 p=argparse.ArgumentParser();p.add_argument('--episode-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 from isaacsim import SimulationApp
 app=SimulationApp({'headless':True});code=1
 try:
  from pxr import Usd,UsdGeom,UsdPhysics
  from isaacsim.core.api import World
  from isaacsim.core.prims import SingleRigidPrim
  from isaacsim.core.utils.stage import open_stage
  from isaacsim.robot.manipulators.examples.franka import Franka
  from isaacsim.core.utils.types import ArticulationAction
  import omni.usd,omni.physx
  initial=json.loads((args.episode_dir/'episode_0000_initial.json').read_text());boxes=json.loads((args.episode_dir/'episode_0000_collision_boxes.json').read_text());checks=[]
  for filename in ['rack.usda','instrument.usda','cuvette.usda','cuvette_debug.usda']:
   st=Usd.Stage.Open(str(args.episode_dir/'assets'/filename));checks.append(dict(asset=filename,loaded=bool(st),meters_per_unit=UsdGeom.GetStageMetersPerUnit(st),up_axis=str(UsdGeom.GetStageUpAxis(st)),collision_count=sum(x.HasAPI(UsdPhysics.CollisionAPI) for x in st.Traverse())))
  open_stage(str(args.episode_dir/'episode_0000_scene.usda'));world=World(stage_units_in_meters=1.,physics_dt=1/240,rendering_dt=1/60);stage=omni.usd.get_context().get_stage()
  robot=world.scene.add(Franka(prim_path='/World/Franka',name='reload_robot'));cup=world.scene.add(SingleRigidPrim(prim_path='/World/Cuvette',name='reload_cup'));q=np.array(initial['joints']);robot.set_joints_default_state(positions=q)
  state=initial['objects']['target'];cup.set_default_state(position=np.array(state['position']),orientation=np.array(state['orientation']))
  errors=[]
  for _ in range(2):
   world.reset();robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=q));p0=cup.get_world_pose()[0];errors.append(float(np.linalg.norm(p0-state['position'])))
   for j in range(30):world.step(render=False)
  query=omni.physx.get_physx_scene_query_interface();t=np.array(initial['target_m']);ray=query.raycast_closest(tuple(t+[0,0,.024]),(0.,0.,-1.),.04);floor=float(ray['position'][2]);dimensions=[]
  for b in boxes:
   prim=stage.GetPrimAtPath(b['prim']);c=UsdGeom.Cube(prim);scale=np.array(prim.GetAttribute('xformOp:scale').Get());size=float(c.GetSizeAttr().Get())*scale;dimensions.append(dict(id=b['id'],error_m=float(np.max(abs(size-b['size']))),native_cube=bool(c)))
  report=dict(assets=checks,actual_reset_position_errors_m=errors,reset_tolerance_m=1e-6,holder_center_ray=dict(hit=ray['hit'],collision=str(ray.get('collision')),z_m=floor,expected_m=float(t[2])),native_collision_dimensions=dimensions,complete_runtime_cooked_geometry_dump=False)
  report['passed']=all(x['loaded'] and x['meters_per_unit']==1. for x in checks) and max(errors)<1e-6 and abs(floor-t[2])<1e-5 and max(x['error_m'] for x in dimensions)<1e-6
  args.output.write_text(json.dumps(report,indent=2));print('USD_RELOAD_RESET',report['passed'],flush=True);code=0 if report['passed'] else 1
 except BaseException:traceback.print_exc();raise
 finally:
  from omni.kit.app import get_app
  get_app().post_quit(code);app.close()
if __name__=='__main__':main()
