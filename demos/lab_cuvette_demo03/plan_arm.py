"""Zero-physics Lula IK/FK whole-arm input-envelope path diagnostic.

Searches a small set of robot mount/IK seed choices, preserving all assets and
TCP orientation. No dynamic object is attached, moved or simulated here.
"""
from pathlib import Path
import argparse,json,sys
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from demos.lab_cuvette_external.run import write

def diagnose(cfg,out):
    import omni.usd
    from pxr import UsdGeom
    from scipy.spatial.transform import Rotation
    from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver,interface_config_loader
    from demos.lab_cuvette_demo03.arm_geometry import load_collision_model,collision_local_points,TriangleMeshIndex
    from demos.lab_cuvette_demo03.preflight import instrument_triangles,_box_hits
    from demos.lab_cuvette_demo03.scene import layout
    omni.usd.get_context().new_stage();UsdGeom.SetStageMetersPerUnit(omni.usd.get_context().get_stage(),1.)
    kin=LulaKinematicsSolver(**interface_config_loader.load_supported_lula_kinematics_solver_config('Franka'))
    model=load_collision_model();local=collision_local_points(model)
    local={k:np.array([[x,y,z] for x in [v[:,0].min(),v[:,0].max()] for y in [v[:,1].min(),v[:,1].max()] for z in [v[:,2].min(),v[:,2].max()]]) for k,v in local.items()}
    d=layout(cfg);stage,records=instrument_triangles(cfg);indexes={r['path']:TriangleMeshIndex(r['triangles'].reshape(-1,3),np.arange(r['triangles'].size//3).reshape(-1,3)) for r in records};source=d['source_floor'];dest=d['target_floor'];g=cfg.robot.grasp_above_bottom_m;z=cfg.control.transport_bottom_z_m+g
    initial=source+[0,0,.28];anchor=source+[0,0,g];lift=np.r_[source[:2],z];corner=np.array([source[0],dest[1],z]);transport=np.r_[dest[:2],z];load=dest+[0,0,g]
    raised=load+np.array([0,0,cfg.control.get('retreat_lift_m',.06)]);withdrawn=raised+np.r_[cfg.control.get('retreat_lateral_m',[-.12,0]),0.]
    segments=[('approach',initial,anchor,.04),('extract',anchor,lift,.0075),('around_lid',lift,corner,.0075),('enter',corner,transport,.0075),('insert',transport,load,.0075),('open',load,load,.04),('retreat_lift',load,raised,.04),('retreat_outward',raised,withdrawn,.04)]
    bases=[[-.3,0,.74],[-.3,.2,.74],[-.2,.4,.74],[-.1,.4,.74],[-.3,.4,.74]]
    seeds=[np.array([0.,-.785,0.,-2.356,0.,1.571,.785]),np.array([0.,-.785,1.,-2.356,0.,1.571,.785]),np.array([0.,-.785,-1.,-2.356,0.,1.571,.785])]
    candidates=[];chosen=None
    for base in bases:
      kin.set_robot_base_pose(np.array(base),np.array([1.,0,0,0]))
      for seed_index,seed in enumerate(seeds):
        q,valid=kin.compute_inverse_kinematics('right_gripper',initial,np.array([0.,1.,0,0]),warm_start=seed,position_tolerance=5e-5,orientation_tolerance=.003)
        initial_q=q.copy();hits=[];fail=None;max_delta=0.
        if not valid:fail='initial IK'
        for phase,a,b,finger in segments if valid else []:
          for frac in np.linspace(0,1,25):
            target=a+(b-a)*frac;next_q,ok=kin.compute_inverse_kinematics('right_gripper',target,np.array([0.,1.,0,0]),warm_start=q,position_tolerance=5e-5,orientation_tolerance=.003)
            if not ok:fail='IK '+phase;break
            max_delta=max(max_delta,float(np.max(abs(next_q-q))));q=next_q
            for name,v in local.items():
                if 'finger' in name:
                    hp,hr=kin.compute_forward_kinematics('panda_hand',q);lp=np.array([0,(1 if name=='panda_leftfinger' else -1)*finger,.05839997]);p=hp+hr@lp;rot=hr
                else:p,rot=kin.compute_forward_kinematics(name,q)
                points=v@rot.T+p;collisions=_box_hits(records,points.min(0),points.max(0))
                if collisions:
                    confirmed=[]
                    for mesh in model['links'][name]['meshes']:
                        world=mesh['vertices_local_m']@rot.T+p
                        faces=mesh['convex_hull_faces_input'] if mesh['approximation_authored']=='convexHull' else mesh['faces']
                        for c in collisions:
                            check=indexes[c['path']].intersections(world,faces,max_witnesses=2)
                            if check['surface_contact_or_crossing']:confirmed.append(dict(path=c['path'],check=check))
                    if confirmed:hits.append(dict(phase=phase,fraction=float(frac),tcp_target=target,joints=q.copy(),link=name,hits=confirmed))
            if hits:break
          if fail or hits:break
        passed=not fail and not hits and max_delta<.45
        result=dict(base_m=base,seed_index=seed_index,initial_arm_q=initial_q,passed=passed,ik_failure=fail,first_collision=hits[:3],max_sample_joint_delta_rad=max_delta)
        candidates.append(result);print('ARM_CANDIDATE',base,seed_index,passed,fail,[(h['phase'],h['link']) for h in hits[:2]],flush=True)
        if passed:chosen=result;break
      if chosen:break
    result=dict(version='V0_demo03',method='Lula IK/FK25 samples per segment; all11 collision-bearing rigid links; AABB broadphase followed by reconstructed declared input-hull triangle SAT vs retained original instrument triangles; no physics',candidates=candidates,selected=chosen,transport_bottom_z_m=cfg.control.transport_bottom_z_m,physics_steps=0,cooked_geometry_readback=False,limitations=['No dynamic grasp or tracking/contact validation; actual task still required.','Input vertex AABBs are conservative and are not cooked convex buffers.','Rasterized source rack and blue neighbor are checked during actual execution; this plan screens instrument/lid.'])
    write(out/'arm_plan.json',result)
    if chosen:write(out/'selected_initial_state.json',dict(joints=np.r_[chosen['initial_arm_q'],.04,.04],robot_base_m=chosen['base_m']))
    return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_demo03/video_demo_adapted.yaml');p.add_argument('--output',type=Path,required=True);p.add_argument('--bottom-z',type=float);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 from isaacsim import SimulationApp
 app=SimulationApp(dict(headless=True,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
 try:
  cfg=OmegaConf.load(a.config)
  if a.bottom_z is not None:cfg.control.transport_bottom_z_m=a.bottom_z
  diagnose(cfg,a.output)
 finally:app.close()
if __name__=='__main__':main()
