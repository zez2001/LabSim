"""Validate external measurements/records and create a new configuration version."""
import argparse,json,copy,datetime
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
JOINTS=[f'panda_joint{i}' for i in range(1,8)]+['panda_finger_joint1','panda_finger_joint2']
UNITS={'m':1.,'mm':.001,'kg':1.,'g':.001,'rad':1.,'deg':np.pi/180,'s':1.,'ms':.001,'cm':.01,'1':1.,'Hz':1.,'N':1.,'N*m':1.,'N/m':1.,'N*s/m':1.,'N*m/rad':1.,'N*m*s/rad':1.,'kg*m^2':1.,'rad/s':1.,'m/s':1.,'mixed_SI':1.}
def normalize_record(record):
 if record['purpose'] not in ['calibration','model_selection','final_validation']:raise ValueError('explicit data purpose required')
 if record['robot_type']!='franka_proxy':raise ValueError('Cross-robot absolute joint import rejected: replace model/control adapter first')
 if record['world_frame']!='LabSim_Z_up_metres' or record['quaternion_order']!='wxyz':raise ValueError('supply an explicit validated coordinate transform before import')
 names=record['joint_names']
 if sorted(names)!=sorted(JOINTS):raise ValueError('joint names mismatch')
 if record['action_semantics']!='absolute_joint_position':raise ValueError('unsupported command semantics')
 if record['angular_unit'] not in ['rad','deg'] or record['linear_unit'] not in ['m','mm'] or record['time_unit'] not in ['s','ms']:raise ValueError('unit dimension mismatch')
 order=[names.index(j) for j in JOINTS];q=np.array(record['joint_states'],float)[:,order];a=np.array(record['commands'],float)[:,order]
 if q.ndim!=2 or q.shape[1]!=9 or a.shape!=q.shape:raise ValueError('9D states/commands required; both fingers explicit')
 q[:,:7]*=UNITS[record['angular_unit']];a[:,:7]*=UNITS[record['angular_unit']];q[:,7:]*=UNITS[record['linear_unit']];a[:,7:]*=UNITS[record['linear_unit']]
 t=np.array(record['timestamps'],float)*UNITS[record['time_unit']]
 if len(t)!=len(q) or not np.all(np.diff(t)>0) or not np.isfinite(np.r_[t,q.ravel(),a.ravel()]).all():raise ValueError('nonfinite or nonmonotonic record')
 if np.any(q[:,7:]<0) or np.any(q[:,7:]>.04) or np.any(a[:,7:]<0) or np.any(a[:,7:]>.04):raise ValueError('finger range violation')
 return dict(schema='LabSim.real_record.v1',synthetic_fixture=bool(record.get('synthetic_fixture',False)),purpose=record['purpose'],robot_type=record['robot_type'],joint_names=JOINTS,timestamps_s=(t-t[0]).tolist(),joint_states_SI=q.tolist(),commands_SI=a.tolist(),events=record.get('events',[]),results=record.get('results',{}),source_units={k:record[k] for k in ['angular_unit','linear_unit','time_unit']},world_frame=record['world_frame'],source_calibrated=record.get('calibrated',False))
def patch_config(base,measurements):
 cfg=OmegaConf.to_container(OmegaConf.load(base),resolve=True);history=[]
 if measurements['version']=='V0':raise ValueError('V0 is immutable; import into a new version')
 if measurements['purpose']=='final_validation':raise ValueError('final validation data cannot tune parameters')
 for item in measurements['parameters']:
  keys=item['name'].split('.');parent=cfg
  for key in keys[:-1]:parent=parent[key]
  key=keys[-1]
  if key not in parent:raise ValueError('unknown parameter '+item['name'])
  if item['unit'] not in UNITS:raise ValueError('unsupported unit')
  special={'focal_length':'cm','arm_kp':'N*m/rad','arm_kd':'N*m*s/rad','finger_kp':'N/m','finger_kd':'N*s/m','max_velocity':'mixed_SI','max_effort':'mixed_SI'}
  expected=special.get(key)
  if expected is None:
   expected=next((u for suffix,u in [('_kg_m2','kg*m^2'),('_mm','mm'),('_m','m'),('_kg','kg'),('_deg','deg'),('_rad','rad'),('_hz','Hz'),('_s','s'),('_seconds','s')] if key.endswith(suffix)), 'Hz' if key=='hz' else '1')
  compatible=[{'m','mm','cm'},{'kg','g'},{'rad','deg'},{'s','ms'}]
  if not (item['unit']==expected or any(item['unit'] in g and expected in g for g in compatible)):raise ValueError('unit dimension mismatch: '+item['name'])
  value=np.asarray(item['value'])*UNITS[item['unit']]/UNITS[expected]
  if not np.isfinite(value).all():raise ValueError('nonfinite parameter')
  if key in ['size_m','size_xy_m','wall_m','inner_m','depth_m','pitch_m','mass_kg','inertia_diagonal_kg_m2','arm_kp','arm_kd','finger_kp','finger_kd','max_effort','max_velocity','focal_length'] and np.any(value<=0):raise ValueError('positive physical parameter required')
  if key in ['rows','columns','resolution']:
   if not np.all(value==np.round(value)):raise ValueError('integer parameter required')
   value=value.astype(int)
  value=value.tolist();history.append(dict(name=item['name'],old=parent[key],new=value,source=item['source'],unit_config=expected,source_type=item['source_type']));parent[key]=value
 cfg['version']=measurements['version'];cfg['calibrated']=False
 return cfg,dict(base_version='V0',new_version=cfg['version'],purpose=measurements['purpose'],changes=history,created=datetime.datetime.now().isoformat(),required_revalidation=['standard','random_distribution','scoring','old_replay','independent_real_validation'],validation_complete=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--record',type=Path);p.add_argument('--measurements',type=Path);p.add_argument('--base',type=Path,default=Path('config/lab_cuvette_loading/V0.yaml'));p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 if args.record:(args.output/'normalized_record.json').write_text(json.dumps(normalize_record(json.loads(args.record.read_text())),indent=2))
 if args.measurements:
  cfg,history=patch_config(args.base,json.loads(args.measurements.read_text()));OmegaConf.save(OmegaConf.create(cfg),args.output/'config.yaml');(args.output/'parameter_history.json').write_text(json.dumps(history,indent=2))
if __name__=='__main__':main()
