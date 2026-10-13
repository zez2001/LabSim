"""Sequential precision insertion experiments on one GPU, using existing collectors."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=ROOT/'config/minimal_precision_insertion.yaml')
    p.add_argument('--output',type=Path)
    p.add_argument('--offsets',default='0')
    p.add_argument('--physics-hz',default='120')
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--headless',action='store_true')
    p.add_argument('--no-video',action='store_true')
    p.add_argument('--keep-open',action='store_true',help='Pause the final scene for GUI inspection after recording')
    p.add_argument('--contact-offset-mm',type=float)
    p.add_argument('--position-iterations',type=int)
    p.add_argument('--tube-segments',type=int)
    p.add_argument('--diagnostic',action='store_true',help='No-contact small-motion diagnostic instead of insertion')
    return p.parse_args()


def jsonwrite(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def run(args,app):
    from datetime import datetime
    from omegaconf import OmegaConf
    import numpy as np
    from tasks.minimal_precision_insertion_task import MinimalPrecisionInsertionTask
    from controllers.minimal_precision_insertion_controller import MinimalPrecisionInsertionController
    from data_collectors.minimal_precision_insertion_collector import MinimalPrecisionInsertionCollector
    output=(args.output or ROOT/'outputs/minimal_precision_insertion'/datetime.now().strftime('%Y%m%d_%H%M%S')).resolve()
    output.mkdir(parents=True,exist_ok=False)
    import shutil
    for p in list((ROOT/'demos/minimal_precision_insertion').glob('*.py'))+[ROOT/'config/minimal_precision_insertion.yaml',
            ROOT/'tasks/minimal_precision_insertion_task.py',ROOT/'controllers/minimal_precision_insertion_controller.py',
            ROOT/'data_collectors/minimal_precision_insertion_collector.py']:
        target=output/'source_snapshot'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
    base=OmegaConf.load(args.config)
    if args.contact_offset_mm is not None:
        base.physics.contact_offset_m=args.contact_offset_mm*.001
    if args.position_iterations is not None:
        base.physics.position_iterations=args.position_iterations
    if args.tube_segments is not None:
        base.geometry.tube_segments=args.tube_segments
    jsonwrite(output/'version.json',dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        python=sys.version,git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            list((ROOT/'demos/minimal_precision_insertion').glob('*.py'))+[ROOT/'config/minimal_precision_insertion.yaml',
            ROOT/'tasks/minimal_precision_insertion_task.py',ROOT/'controllers/minimal_precision_insertion_controller.py',
            ROOT/'data_collectors/minimal_precision_insertion_collector.py']}))
    results=[]
    for hz in [int(x) for x in args.physics_hz.split(',')]:
        cfg=OmegaConf.create(OmegaConf.to_container(base));cfg.physics.hz=hz
        if args.diagnostic:
            cfg.task.initial_tcp[2]+=.050
        group=output/f'physics_{hz}';group.mkdir()
        OmegaConf.save(cfg,group/'config.yaml')
        task=MinimalPrecisionInsertionTask(cfg,group/'assets')
        recorder=MinimalPrecisionInsertionCollector(cfg,group,save_video=not args.no_video)
        if not args.headless:
            from omni.kit.viewport.utility import get_active_viewport
            viewport=get_active_viewport()
            if viewport is not None:
                viewport.camera_path=cfg.cameras[0].prim_path
                jsonwrite(group/'gui_viewport.json',dict(camera_path=str(viewport.camera_path)))
        try:
            if args.diagnostic:
                diagnostic=[]
                for index,delta in enumerate((.1,.5,1.,2.)):
                    diagnostic_started=time.monotonic()
                    task.reset(0.)
                    jsonwrite(group/f'episode_{index:04d}_initial.json',dict(displacement_mm=delta,
                        nominal_offset_mm=0.,repeat=0,hole_center_m=task.hole_center.tolist(),
                        state=task.initial_state,joints=task.robot.get_joint_positions().tolist()))
                    jsonwrite(group/f'episode_{index:04d}_collision_snapshot.json',task.cooked_snapshot())
                    jsonwrite(group/'effective_parameters.json',task.parameter_snapshot())
                    controller=MinimalPrecisionInsertionController(cfg,task.robot,task)
                    recorder.begin_episode(index,task.initial_position)
                    initial_tcp=task.initial_tcp.copy()
                    measured=[]
                    execution_started=time.monotonic()
                    for frame in range(180):
                        target=np.array(cfg.task.initial_tcp)
                        target[0]+=delta*.001*min(frame/60.,1.)
                        task.diagnostic_target=target
                        state=task.step();action=controller.step(state)
                        if action is None:
                            break
                        state.update(target_tcp=target.copy(),ik_residual_m=controller.last_ik_residual,phase=task.phase)
                        task.advance(action);next_state=task.step()
                        if task.status!='RUNNING':
                            raise RuntimeError('Free-motion diagnostic terminated: '+task.status+' '+task.reason)
                        if frame==179:
                            task.status,task.reason='DIAGNOSTIC_COMPLETE','free_motion_not_an_insertion_success'
                        recorder.cache_transition(state,action,next_state,task.result())
                        measured.append(dict(time=task.elapsed,target=target.tolist(),actual=next_state['tcp'].tolist(),
                            ik_residual=controller.last_ik_residual,joint_error=float(np.max(np.abs(next_state['joint_positions'][:7]-action.joint_positions[:7]))),
                            module_contact=next_state['metrics']['module_contact_N']))
                    stable=measured[-60:]
                    if len(measured)!=180:
                        raise RuntimeError('Free-motion diagnostic did not complete all control steps')
                    xyz=np.array([m['actual'] for m in stable])
                    targets=np.array([m['target'] for m in stable])
                    row=dict(displacement_mm=delta,physics_hz=hz,actual_displacement_mm=float((xyz.mean(axis=0)[0]-initial_tcp[0])*1000),
                        max_ik_residual_mm=max(m['ik_residual'] for m in stable)*1000,
                        mean_tcp_error_mm=float(np.linalg.norm(xyz-targets,axis=1).mean()*1000),
                        max_joint_tracking_error_rad=max(m['joint_error'] for m in stable),
                        hold_jitter_peak_to_peak_mm=(np.ptp(xyz,axis=0)*1000).tolist(),
                        max_environment_contact_N=max(m['module_contact'] for m in measured),
                        simulation_seconds=task.elapsed,engine_simulation_seconds=task.world.current_time-task.clock_origin,
                        wall_clock_seconds=time.monotonic()-diagnostic_started,
                        execution_wall_seconds=time.monotonic()-execution_started)
                    task.status,task.reason='DIAGNOSTIC_COMPLETE','free_motion_not_an_insertion_success'
                    recorder.finish_episode(dict(task.result(),diagnostic=row))
                    with (group/f'episode_{index:04d}_physics.jsonl').open('w') as f:
                        for record in task.substep_records:f.write(json.dumps(record)+'\n')
                    task.events.append(dict(event='TERMINATED',time=task.elapsed,status=task.status,reason=task.reason))
                    jsonwrite(group/f'episode_{index:04d}_events.json',task.events)
                    jsonwrite(group/f'diagnostic_{index:04d}.json',measured)
                    diagnostic.append(row)
                    print('DIAGNOSTIC '+json.dumps(row),flush=True)
                jsonwrite(group/'diagnostic_summary.json',diagnostic)
                continue
            for index,(offset,repeat) in enumerate([(float(x),r) for x in args.offsets.split(',') for r in range(args.repeats)]):
                start=time.monotonic()
                task.reset(offset)
                cooking=task.cooked_snapshot()
                jsonwrite(group/f'episode_{index:04d}_collision_snapshot.json',cooking)
                jsonwrite(group/'effective_parameters.json',task.parameter_snapshot())
                if index==0:
                    probe=task.runtime_geometry_probe()
                    jsonwrite(group/'runtime_geometry_probe.json',probe)
                    if len(probe['sampled_inner_radius_range_m'])!=2 or max(abs(x-probe['expected_polygon_apothem_m']) for x in probe['sampled_inner_radius_range_m'])>1e-5:
                        raise RuntimeError('Runtime hole ray dimensions fail the 10 um geometry gate')
                    if cfg.geometry.collision=='compound_convex' and not cooking['tube_cooked_available']:
                        raise RuntimeError('Cannot read back all tube convex sectors')
                    jsonwrite(group/'tube_runtime_probe.json',task.tube_runtime_probe())
                    from demos.minimal_precision_insertion.effective import tube_radial_probe
                    tube_probe=tube_radial_probe(task.tube)
                    jsonwrite(group/'tube_radial_probe.json',tube_probe)
                    if tube_probe['radial_sample_count']!=384 or tube_probe['sampled_max_radius_error_m']>1e-5:
                        task.status,task.reason='PHYSICS_INVALID','runtime_tube_boundary_fails_10um_geometry_gate'
                        jsonwrite(group/'geometry_gate_result.json',dict(status=task.status,reason=task.reason,
                            operation_started=False,probe=tube_probe))
                        print('PHYSICS_INVALID geometry_gate: tube runtime boundary does not match declared geometry',flush=True)
                        return 1
                    task.save_collision_debug(group/'collision_debug.png')
                    task.stage.Flatten().Export(str(group/'initial_scene.usda'))
                    # Verify independent standalone reload without replacing the live stage.
                    from pxr import Usd,UsdGeom
                    loaded=Usd.Stage.Open(str(group/'initial_scene.usda'))
                    jsonwrite(group/'usd_reload_check.json',dict(default_prim=str(loaded.GetDefaultPrim().GetPath()),
                        units=UsdGeom.GetStageMetersPerUnit(loaded),
                        references=sum(p.HasAuthoredReferences() for p in loaded.Traverse()),
                        tube_bounds=str(UsdGeom.BBoxCache(0,['default','guide']).ComputeLocalBound(loaded.GetPrimAtPath('/World/Tube')).GetRange()),
                        mass=loaded.GetPrimAtPath('/World/Tube').GetAttribute('physics:mass').Get()))
                controller=MinimalPrecisionInsertionController(cfg,task.robot,task)
                recorder.begin_episode(index,task.initial_position)
                state=task.step()
                jsonwrite(group/f'episode_{index:04d}_initial.json',dict(nominal_offset_mm=offset,repeat=repeat,
                    hole_center_m=task.hole_center.tolist(),state=task.initial_state,
                    joints=task.robot.get_joint_positions().tolist(),target_tcp=list(cfg.task.initial_tcp)))
                execution_started=time.monotonic()
                while task.status=='RUNNING' and app.is_running():
                    action=controller.step(state)
                    if action is None:
                        break
                    # Action target must be the one computed for this observation, before advancing.
                    state['target_tcp']=controller.last_target.copy()
                    state['ik_residual_m']=controller.last_ik_residual
                    state['phase']=task.phase
                    task.advance(action)
                    next_state=task.step()
                    if task.elapsed>=24. and not (group/f'episode_{index:04d}_gripper_clearance.json').exists():
                        from demos.minimal_precision_insertion.effective import gripper_vertical_clearance
                        try:
                            clearance=gripper_vertical_clearance(task.world,task.stage,cfg.task.floor_z+.02)
                            clearance['time_s']=task.elapsed
                        except Exception as error:
                            clearance=dict(verified=False,error=str(error))
                        jsonwrite(group/f'episode_{index:04d}_gripper_clearance.json',clearance)
                    result=task.result()
                    recorder.cache_transition(state,action,next_state,result)
                    state=next_state
                    if task.frame_idx%300==0:
                        print(f"STATE hz={hz} offset={offset} repeat={repeat} t={task.elapsed:.1f} "
                              f"depth={task.max_depth*1000:.3f} overlap={task.max_overlap*1000:.4f} "
                              f"xy={task.last_metrics['xy_error_m']} slip={task.max_slip*1000:.3f}",flush=True)
                    if time.monotonic()-start>max(300,cfg.task.timeout_seconds*30):
                        task.status,task.reason='TIMEOUT','wall_clock_watchdog'
                if task.status=='RUNNING':
                    task.status,task.reason='CONTROL_OR_IK_FAILURE','application_stopped'
                task.events.append(dict(event='TERMINATED',time=task.elapsed,status=task.status,reason=task.reason))
                if task.status=='PHYSICS_INVALID':
                    jsonwrite(group/f'episode_{index:04d}_terminal_runtime_probe.json',task.tube_runtime_probe())
                result=task.result();result.update(repeat=repeat,wall_clock_seconds=time.monotonic()-start,
                    execution_wall_seconds=time.monotonic()-execution_started,setup_wall_seconds=execution_started-start,
                    output=str(group),episode=f'episode_{index:04d}')
                recorder.finish_episode(result)
                with (group/f'episode_{index:04d}_physics.jsonl').open('w') as f:
                    for record in task.substep_records:
                        f.write(json.dumps(record)+'\n')
                jsonwrite(group/f'episode_{index:04d}_events.json',task.events)
                results.append(result)
                jsonwrite(output/'summary.json',results)
                print(result['status']+' '+json.dumps({k:result[k] for k in
                    ('physics_hz','nominal_offset_mm','repeat','reason','simulation_seconds','max_depth_mm','max_overlap_mm','episode')}),flush=True)
                # Failed centre insertion is a hard gate before any offset batch.
                if offset==0. and result['status']!='SUCCESS' and len(args.offsets.split(','))>1:
                    print('CENTER_GATE_FAILED: remaining offsets are not run',flush=True)
                    return 1
            recorder.merge()
        finally:
            recorder.close()
    if getattr(args,'keep_open',False) and not args.headless:
        task.world.pause()
        print('GUI_PAUSED: close the Isaac window to finish; recording is already complete',flush=True)
        while app.is_running():task.world.render()
    columns=['physics_hz','nominal_offset_mm','repeat','status','reason','precontact_x_mm','precontact_y_mm',
             'precontact_tilt_deg','max_depth_mm','final_depth_mm','max_overlap_mm','max_grasp_slip_mm','simulation_seconds','wall_clock_seconds','episode']
    with (output/'results.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for r in results:
            pre=r['actual_precontact'] or r['initial_state']
            row={k:r[k] for k in columns if k in r}
            row.update(precontact_x_mm=pre['xy_error_m'][0]*1000,precontact_y_mm=pre['xy_error_m'][1]*1000,
                       precontact_tilt_deg=np.degrees(pre['tilt_rad']),final_depth_mm=r['final_state']['depth_m']*1000)
            writer.writerow(row)
    print('EXPERIMENT_SAVED '+str(output),flush=True)
    return 0


def main():
    args=arguments()
    # A fresh app per frequency avoids dangling render products on stage replacement.
    # Parent owns no Isaac/RTX context; subprocess.run makes GPU work sequential.
    frequencies=args.physics_hz.split(',')
    if len(frequencies)>1:
        from datetime import datetime
        output=(args.output or ROOT/'outputs/minimal_precision_insertion'/datetime.now().strftime('%Y%m%d_%H%M%S')).resolve()
        output.mkdir(parents=True,exist_ok=False)
        codes=[];combined=[]
        for frequency in frequencies:
            command=[sys.executable,str(Path(__file__).resolve()),'--config',str(args.config),
                '--output',str(output/f'hz_{frequency}'),'--physics-hz',frequency,
                '--offsets',args.offsets,'--repeats',str(args.repeats)]
            for name in ('headless','no_video','diagnostic','keep_open'):
                if getattr(args,name):
                    command.append('--'+name.replace('_','-'))
            for name in ('contact_offset_mm','position_iterations','tube_segments'):
                if getattr(args,name) is not None:
                    command.extend(['--'+name.replace('_','-'),str(getattr(args,name))])
            with (output/f'hz_{frequency}.log').open('w') as log:
                codes.append(subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT).returncode)
            summary=output/f'hz_{frequency}'/'summary.json'
            if summary.exists():
                combined.extend(json.loads(summary.read_text()))
            print('CONFIGURATION_FINISHED '+frequency+' exit='+str(codes[-1]),flush=True)
        jsonwrite(output/'summary.json',combined)
        return 0 if all(c==0 for c in codes) else 1
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,
        extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    code=1
    try:
        code=run(args,app)
    except Exception:
        import traceback
        traceback.print_exc()
        print('CONTROL_OR_IK_FAILURE runner_exception',flush=True)
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(code)
        app.close()
    return code


if __name__=='__main__':
    sys.exit(main())
