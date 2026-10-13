"""Load the exported scene in a fresh PhysX app and verify three physical resets.

Initialization writes are confined to reset. This is an asset validation, not an
insertion episode, and does not contribute to insertion outcome statistics.
"""
import argparse
import json
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('group',type=Path,help='A physics_120 output directory')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--headless',action='store_true')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    code=1
    try:
        import numpy as np
        import omni.usd
        import omni.physx
        import carb
        carb.settings.get_settings().set_bool('/physics/collisionApproximateCylinders',False)
        from pxr import Usd,UsdGeom,UsdPhysics
        from omegaconf import OmegaConf
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleRigidPrim
        from isaacsim.core.utils.stage import open_stage,is_stage_loading
        from isaacsim.core.utils.types import ArticulationAction
        from isaacsim.robot.manipulators.examples.franka import Franka
        cfg=OmegaConf.load(args.group/'config.yaml')
        # Automated costs are measured separately from engineering work. They
        # must never be presented as the time needed to implement/debug an asset.
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from demos.minimal_precision_insertion.geometry import cylinder_mesh,annulus_mesh,create_assets
        begin=time.perf_counter()
        cylinder_mesh(.005,.05,cfg.geometry.tube_segments)
        annulus_mesh(.0053,.009,.02,cfg.geometry.hole_segments)
        profile=dict(geometry_array_creation_seconds=time.perf_counter()-begin)
        begin=time.perf_counter();create_assets(args.output/'regenerated_assets',cfg)
        profile['usd_authoring_collision_mass_material_and_save_seconds']=time.perf_counter()-begin
        profile['limitation']='Automated rebuild costs; implementation/debugging categories were interleaved and not individually timed.'
        initial=json.loads((args.group/'episode_0000_initial.json').read_text())
        standalone={}
        begin=time.perf_counter()
        for name in ('tube','module'):
            stage=Usd.Stage.Open(str(args.group/'assets'/(name+'.usda')))
            root=stage.GetDefaultPrim()
            standalone[name]=dict(default_prim=str(root.GetPath()),units=UsdGeom.GetStageMetersPerUnit(stage),
                references=sum(p.HasAuthoredReferences() for p in stage.Traverse()),
                visual_bound=str(UsdGeom.BBoxCache(0,['default']).ComputeLocalBound(root).GetRange()),
                collision_bound=str(UsdGeom.BBoxCache(0,['guide']).ComputeLocalBound(root).GetRange()),
                collision_count=sum(p.HasAPI(UsdPhysics.CollisionAPI) for p in stage.Traverse()))
        assert standalone['tube']['references']==standalone['module']['references']==0
        profile['standalone_usd_reload_and_bound_seconds']=time.perf_counter()-begin
        assert open_stage(str(args.group/'initial_scene.usda'))
        while is_stage_loading():
            app.update()
        world=World(stage_units_in_meters=1.,physics_dt=1/cfg.physics.hz,rendering_dt=1/60,backend='numpy',device='cpu')
        robot=world.scene.add(Franka(prim_path='/World/Franka',name='reload_franka'))
        tube=world.scene.add(SingleRigidPrim(prim_path='/World/Tube',name='reload_tube'))
        q=np.array(initial['joints'])
        robot.set_joints_default_state(positions=q)
        query=omni.physx.get_physx_scene_query_interface()
        repeats=[]
        for repeat in range(3):
            reset_begin=time.perf_counter()
            world.reset()
            robot.set_joint_positions(q);robot.set_joint_velocities(np.zeros(9))
            tube.set_world_pose(np.array(initial['state']['position']),np.array(initial['state']['orientation']))
            tube.set_linear_velocity(np.zeros(3));tube.set_angular_velocity(np.zeros(3))
            target=q.copy();target[7:]=0.
            robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=target))
            start=world.current_time
            for step in range(cfg.physics.hz):
                world.step(render=False)
                if (step+1)%(cfg.physics.hz//60)==0:
                    world.render()
            hole=initial['hole_center_m'];hits=[]
            for z in (.002,.010,.018):
                for i in range(cfg.geometry.hole_segments):
                    a=(i+.47)*2*np.pi/cfg.geometry.hole_segments
                    hit=query.raycast_closest(tuple(hole)+(cfg.task.floor_z+z,),
                        (float(np.cos(a)),float(np.sin(a)),0.),.015,True)
                    assert hit['hit'] and hit['collision']=='/World/Module/WallCollision'
                    hits.append(hit['distance'])
            apothem=.0053*np.cos(np.pi/cfg.geometry.hole_segments)
            assert max(abs(x-apothem) for x in hits)<1e-5
            mass=omni.physx.get_physxunittests_interface().get_mass_information('/World/Tube')
            info=dict(repeat=repeat,actual_seconds=world.current_time-start,
                reset_and_one_second_validation_wall_seconds=time.perf_counter()-reset_begin,
                tube_pose=[x.tolist() for x in tube.get_world_pose()],
                hole_inner_radius_range_m=[min(hits),max(hits)],
                runtime_mass={k:np.asarray(v).tolist() for k,v in mass.items()},
                stats=omni.physx.get_physxunittests_interface().get_physics_stats())
            assert np.isclose(info['actual_seconds'],1.,atol=1e-6)
            repeats.append(info)
        result=dict(status='RELOAD_RESET_VERIFIED',standalone=standalone,resets=repeats,
            limitation='Sampled runtime cavity dimensions; not a full cooked triangle dump or a new insertion trial.')
        from effective import runtime_shape_parameters,tube_radial_probe
        result['runtime_shapes']=runtime_shape_parameters(world,robot)
        result['tube_runtime_radial_probe']=tube_radial_probe(tube)
        result['tube_dimension_gate_passed']=(result['tube_runtime_radial_probe']['radial_sample_count']==384
            and result['tube_runtime_radial_probe']['sampled_max_radius_error_m']<=1e-5)
        if not result['tube_dimension_gate_passed']:
            result['status']='RELOAD_RESET_VERIFIED_DIMENSION_MISMATCH'
        (args.output/'reload_validation.json').write_text(json.dumps(result,indent=2)+'\n')
        (args.output/'asset_build_profile.json').write_text(json.dumps(profile,indent=2)+'\n')
        print(result['status'],flush=True)
        code=0 if result['tube_dimension_gate_passed'] else 1
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(code);app.close()
    return code


if __name__=='__main__':
    sys.exit(main())
