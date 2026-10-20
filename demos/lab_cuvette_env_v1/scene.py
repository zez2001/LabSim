"""Shared formal-scene construction reusing the verified physical asset builder."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2]

def episode_config(base,seed=0,options=None):
    cfg=OmegaConf.create(OmegaConf.to_container(base,resolve=True));opts=dict(options or {})
    cfg.env.seed=int(seed);cfg.env.task_type=opts.get('subtask',opts.get('task_type',cfg.env.task_type))
    cfg.env.mode=opts.get('mode',cfg.env.mode)
    if cfg.env.mode=='random':
        rng=np.random.default_rng(seed);cfg.rack.selected_slot_id=list(cfg.randomization.legal_slots)[seed%len(cfg.randomization.legal_slots)]
        dr=rng.uniform(-cfg.randomization.rack_translation_half_range_m,cfg.randomization.rack_translation_half_range_m,2)
        di=rng.uniform(-cfg.randomization.instrument_translation_half_range_m,cfg.randomization.instrument_translation_half_range_m,2)
        cfg.rack.origin_m=(np.asarray(cfg.rack.origin_m)+np.r_[dr,0]).tolist();cfg.scene.instrument_xyz_m=(np.asarray(cfg.scene.instrument_xyz_m)+np.r_[di,0]).tolist()
        cfg.randomization.actual=dict(seed=seed,rack_translation_m=dr.tolist(),instrument_assembly_translation_m=di.tolist(),within_slot_translation_m=[0,0],source_slot_id=cfg.rack.selected_slot_id)
    if opts.get('source_slot_id'):cfg.rack.selected_slot_id=opts['source_slot_id']
    cfg.robot.initial_tcp_m=(layout(cfg)['source_floor']+np.array([0.,0.,.28])).tolist()
    return cfg

def layout(cfg):
    from demos.lab_cuvette_demo04.scene import layout as inherited
    if 'instrument_yaw_deg' not in cfg.scene:raise ValueError('Formal scene requires explicit instrument yaw from reference/layout review')
    return inherited(cfg)

def build_context(cfg,app,output,initial_state=None):
    from demos.lab_cuvette_demo04.run import make_scene
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if initial_state is None and 'initial_joint_positions' in cfg.robot:
        import json
        initial_state=output/'declared_initial_joints.json'
        initial_state.write_text(json.dumps(dict(joints=list(cfg.robot.initial_joint_positions),robot_base_m=list(cfg.robot.base_m)),indent=2)+'\n')
    context=make_scene(SimpleNamespace(initial_state=initial_state),app,output,cfg)
    context['fixtures']=layout(cfg)
    return context
