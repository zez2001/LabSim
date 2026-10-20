"""One LabUtopia task entry for the real teacher and synchronous policy RPC."""
from pathlib import Path
import argparse,json,sys,time,fcntl,subprocess
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2]

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/Env_v1/native.yaml')
    p.add_argument('--mode',choices=['teacher','preview','serve','audit','plan'],default='teacher')
    p.add_argument('--subtask',choices=['loading','preinsert_diagnostic','grasp_hold','extract_transport'])
    p.add_argument('--layout-mode',choices=['standard','random'],default='standard')
    p.add_argument('--seed',type=int,default=0);p.add_argument('--episodes',type=int,default=1)
    p.add_argument('--headless',action='store_true');p.add_argument('--output',type=Path)
    p.add_argument('--initial-state',type=Path);p.add_argument('--port',type=int,default=8097)
    p.add_argument('--preview-seconds',type=float,default=2.)
    p.add_argument('--timeout-seconds',type=float)
    return p

def main(args=None):
    if args is None:args=parser().parse_args()
    from demos.lab_cuvette_env_v1.scene import episode_config
    def ensure_current_audit(config,cache_directory,geometry_site=None):
        path=out/'audit_input.yaml';OmegaConf.save(config,path)
        subprocess.run(['bash',str(ROOT/'demos/lab_cuvette_external/usd_python.sh'),'-m','demos.lab_cuvette_env_v1.geometry_audit','--config',str(path),'--output',str(cache_directory),'--ensure','--geometry-site',str(geometry_site)],cwd=ROOT,check=True)
        latest=json.loads((Path(cache_directory)/'latest.json').read_text())
        return json.loads((Path(cache_directory)/latest['audit_relative_path']).read_text())
    cfg=OmegaConf.load(args.config)
    if args.subtask:cfg.env.task_type=args.subtask
    if args.timeout_seconds is not None:cfg.env.timeout_s=args.timeout_seconds
    cfg.env.mode=args.layout_mode
    out=args.output or ROOT/cfg.output_root/(time.strftime('%Y%m%d_%H%M%S')+'_'+args.mode)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    OmegaConf.save(cfg,out/'launch_config.yaml')
    # Audit runs in the installed USD-only environment, before SimulationApp.
    effective=episode_config(cfg,args.seed,dict(mode=args.layout_mode))
    audit=ensure_current_audit(effective,ROOT/cfg.env.geometry_audit_cache,geometry_site=cfg.env.shapely_site)
    (out/'geometry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    if args.mode=='audit':print('GEOMETRY_AUDIT',audit.get('geometry_valid'),flush=True);return 0
    lock=open('/tmp/labsim-V0_ext01-gpu.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    env=None
    try:
        if args.mode=='plan':
            from demos.lab_cuvette_demo04.plan_arm import diagnose
            r=diagnose(effective,out)
            r['version']='Env_v1';r.pop('config_file_sha256',None)
            r['effective_config_sha256']=__import__('hashlib').sha256(OmegaConf.to_yaml(effective).encode()).hexdigest()
            (out/'arm_plan.json').write_text(json.dumps(r,default=lambda x:x.tolist(),indent=2)+'\n')
            return 0 if r['selected'] else 2
        from factories.task_factory import create_task
        from factories.controller_factory import create_controller
        env=create_task(cfg.task_type,cfg,app,out,geometry_audit=audit,initial_state=args.initial_state)
        if args.mode=='serve':
            from demos.lab_cuvette_env_v1.rpc import serve_environment
            serve_environment(env,port=args.port,ready_path=out/'rpc_ready.json');return 0
        results=[]
        for i in range(args.episodes):
            current=episode_config(cfg,args.seed+i,dict(mode=args.layout_mode))
            if i:env.geometry_audit=ensure_current_audit(current,ROOT/cfg.env.geometry_audit_cache,geometry_site=cfg.env.shapely_site)
            obs,info=env.reset(args.seed+i,dict(subtask=cfg.env.task_type,mode=args.layout_mode,teacher=args.mode=='teacher',policy_id='truth_teacher' if args.mode=='teacher' else 'preview',demonstrator_id='LabCuvetteTeacher'))
            teacher=create_controller(cfg.controller_type,env.cfg,env.ctx['fixtures']);teacher.reset(obs,env.get_debug_observation())
            if args.mode=='preview':
                import cv2
                from pxr import UsdGeom
                for name in env.rig.names:cv2.imwrite(str(env.episode_dir/(name+'_initial.png')),cv2.cvtColor(env.render_camera(name),cv2.COLOR_RGB2BGR))
                env.ctx['stage'].GetRootLayer().Export(str(env.episode_dir/'initial_scene.usda'))
            while app.is_running() and not env.ended:
                if args.mode=='preview':
                    if obs['simulation_time']>=args.preview_seconds:env.finalize_episode('PREVIEW_COMPLETE','DIAGNOSTIC_ONLY');break
                    action=dict(episode_id=obs['episode_id'],observation_step=obs['step_index'],type='joint_position',values=obs['joint_positions'][:7],gripper_opening_m=.08,metadata=dict(phase='PREVIEW'))
                else:
                    action=teacher.act(obs,env.get_debug_observation())
                    if teacher.finished:
                        env.finalize_episode(teacher.status, None if teacher.status.endswith('_COMPLETE') else teacher.status);break
                obs,reward,terminated,truncated,info=env.step(action)
                if env.control_steps%120==0:print('ENV_PROGRESS',i,round(env.t,3),env.phase,env.debug['tilt_deg'],flush=True)
            if not env.ended:env.finalize_episode('APPLICATION_INTERRUPTED','PROCESS_INTERRUPTED')
            env._write(env.episode_dir/'teacher_events.json',teacher.events)
            results.append(env._result);print('ENV_RESULT',json.dumps(env._result,default=str),flush=True)
        env._write(out/'summary.json',results);return 0
    except Exception:
        import traceback;traceback.print_exc();return 1
    finally:
        if env is not None:env.close()
        from omni.kit.app import get_app
        get_app().post_quit(0);app.close();lock.close()

if __name__=='__main__':sys.exit(main())
