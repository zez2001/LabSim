"""Validate external measurements/records and create a new configuration version."""
import argparse,json,copy,datetime
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
JOINTS=[f'panda_joint{i}' for i in range(1,8)]+['panda_finger_joint1','panda_finger_joint2']
UNITS={'m':1.,'mm':.001,'kg':1.,'g':.001,'rad':1.,'deg':np.pi/180,'s':1.,'ms':.001}
def normalize_record(record):
 if record['purpose'] not in ['calibration','model_selection','final_validation']:raise ValueError('explicit data purpose required')
 if record['robot_type']!='franka_proxy':raise ValueError('Cross-robot absolute joint import rejected: replace model/control adapter first')
 if record['world_frame']!='LabSim_Z_up_metres' or record['quaternion_order']!='wxyz':raise ValueError('supply an explicit validated coordinate transform before import')
 names=record['joint_names']
 if sorted(names)!=sorted(JOINTS):raise ValueError('joint names mismatch')
 if record['action_semantics']!='absolute_joint_position':raise ValueError('unsupported command semantics')
 order=[names.index(j) for j in JOINTS];q=np.array(record['joint_states'],float)[:,order];a=np.array(record['commands'],float)[:,order]
 if q.ndim!=2 or q.shape[1]!=9 or a.shape!=q.shape:raise ValueError('9D states/commands required; both fingers explicit')
 q[:,:7]*=UNITS[record['angular_unit']];a[:,:7]*=UNITS[record['angular_unit']];q[:,7:]*=UNITS[record['linear_unit']];a[:,7:]*=UNITS[record['linear_unit']]
 t=np.array(record['timestamps'],float)*UNITS[record['time_unit']]
 if len(t)!=len(q) or not np.all(np.diff(t)>0) or not np.isfinite(np.r_[t,q.ravel(),a.ravel()]).all():raise ValueError('nonfinite or nonmonotonic record')
 if np.any(q[:,7:]<0) or np.any(q[:,7:]>.04) or np.any(a[:,7:]<0) or np.any(a[:,7:]>.04):raise ValueError('finger range violation')
 return dict(schema='LabSim.real_record.v1',purpose=record['purpose'],robot_type=record['robot_type'],joint_names=JOINTS,timestamps_s=(t-t[0]).tolist(),joint_states_SI=q.tolist(),commands_SI=a.tolist(),events=record.get('events',[]),results=record.get('results',{}),source_units={k:record[k] for k in ['angular_unit','linear_unit','time_unit']},world_frame=record['world_frame'],source_calibrated=record.get('calibrated',False))
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
  expected='m' if key.endswith('_m') else 'kg' if key.endswith('_kg') else None
  if expected=='m' and item['unit'] not in ['m','mm'] or expected=='kg' and item['unit'] not in ['kg','g']:raise ValueError('unit dimension mismatch')
  value=np.asarray(item['value'])*UNITS[item['unit']]
  if not np.isfinite(value).all():raise ValueError('nonfinite parameter')
  value=value.tolist();history.append(dict(name=item['name'],old=parent[key],new=value,source=item['source'],unit_SI=expected or item['unit'],source_type=item['source_type']));parent[key]=value
 cfg['version']=measurements['version'];cfg['calibrated']=False
 return cfg,dict(base_version='V0',new_version=cfg['version'],purpose=measurements['purpose'],changes=history,created=datetime.datetime.now().isoformat(),required_revalidation=['standard','random_distribution','scoring','old_replay','independent_real_validation'],validation_complete=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--record',type=Path);p.add_argument('--measurements',type=Path);p.add_argument('--base',type=Path,default=Path('config/lab_cuvette_loading/V0.yaml'));p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 if args.record:(args.output/'normalized_record.json').write_text(json.dumps(normalize_record(json.loads(args.record.read_text())),indent=2))
 if args.measurements:
  cfg,history=patch_config(args.base,json.loads(args.measurements.read_text()));OmegaConf.save(OmegaConf.create(cfg),args.output/'config.yaml');(args.output/'parameter_history.json').write_text(json.dumps(history,indent=2))
if __name__=='__main__':main()
