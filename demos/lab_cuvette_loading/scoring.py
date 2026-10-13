"""Actual-state scorer independent of expert targets and script phases."""
from collections import deque
import numpy as np
from demos.lab_cuvette_loading.model import overlap_all,rz
from demos.minimal_precision_insertion.geometry import rotation

class Scorer:
 def __init__(self,cfg,scene,layout,initial):
  self.cfg,self.scene,self.layout,self.initial=cfg,scene,layout,initial
  expected=np.array(scene['source'])+[0,0,cfg.cuvette.size_m[2]/2]
  actual=np.array(initial['objects']['target']['position'])
  correct=(initial['target_object_id']==cfg.cuvette.target_id and initial['source_slot_id']=='r%dc%d'%tuple(layout['source_slot']) and np.linalg.norm(actual[:2]-expected[:2])<.001 and abs(actual[2]-expected[2])<.0005)
  self.progress=dict(correct_source=bool(correct),grasp=False,extracted=False,transported=False,arrived=False,inserted=False,released=False,retreated=False)
  self.history=deque();self.stable_anchor=None;self.stable_start=None;self.stable_seconds=0.;self.max_overlap=0.;self.max_depth=-1.;self.max_lift=0.;self.blocked_history=deque()
 def measure(self,p,q,tcp,joints,finger,contact):
  cfg=self.cfg;A=rotation(q);h=cfg.cuvette.size_m[2];bottom=np.array(p)-A[:,2]*h/2
  target=self.scene['target'];B=rz(self.layout['instrument_yaw_deg']);local=B.T@(bottom-target)
  overlap,collider=overlap_all(cfg,np.array(p),q,self.scene['boxes'])
  tilt=float(np.arccos(np.clip(A[2,2],-1,1)));yaw=float(np.arctan2(A[1,0],A[0,0]));dyaw=(yaw-np.radians(self.layout['instrument_yaw_deg'])+np.pi)%(2*np.pi)-np.pi
  return dict(position=np.asarray(p).tolist(),orientation=np.asarray(q).tolist(),bottom=bottom.tolist(),depth_m=float(cfg.holder.depth_m-local[2]),xy_error_m=local[:2].tolist(),tilt_rad=tilt,yaw_error_rad=float(dyaw),overlap_m=overlap,overlap_collider=collider,tcp=np.asarray(tcp).tolist(),joint_positions=np.asarray(joints).tolist(),finger_contact_N=np.asarray(finger).tolist(),environment_contact_N=float(contact))
 def update(self,t,m):
  cfg=self.cfg;s=cfg.scoring;h=cfg.cuvette.size_m[2];pg=self.progress;p=np.array(m['position']);bottom=np.array(m['bottom']);finger=np.array(m['finger_contact_N']);j=np.array(m['joint_positions']);tcp=np.array(m['tcp']);source=self.scene['source']
  self.max_overlap=max(self.max_overlap,m['overlap_m']);self.max_depth=max(self.max_depth,m['depth_m']) if np.linalg.norm(m['xy_error_m'])<.015 else self.max_depth;self.max_lift=max(self.max_lift,float(bottom[2]-source[2]))
  pg['grasp']|=bool(np.all(finger>s.grasp_force_N))
  pg['extracted']|=bool(pg['grasp'] and bottom[2]>source[2]+cfg.rack.depth_m+s.extraction_above_rack_m)
  pg['transported']|=bool(pg['extracted'] and np.linalg.norm(bottom[:2]-source[:2])>s.transported_distance_m)
  pg['arrived']|=bool(pg['transported'] and np.linalg.norm(m['xy_error_m'])<.010)
  oriented=(m['tilt_rad']<np.radians(s.orientation_tolerance_deg) and abs(m['yaw_error_rad'])<np.radians(s.orientation_tolerance_deg))
  contained=(np.max(np.abs(np.array(m['xy_error_m'])))<s.xy_tolerance_m and oriented)
  loaded=(s.required_depth_m<=m['depth_m']<=cfg.holder.depth_m+s.penetration_tolerance_m and contained)
  pg['inserted']|=bool(pg['arrived'] and loaded)
  pg['released']|=bool(pg['inserted'] and np.all(j[7:]>.030) and np.all(finger<.01))
  away=(np.linalg.norm(tcp-p)>s.retreat_distance_m and tcp[2]>cfg.layout.shell_top_z_m+.04)
  pg['retreated']|=bool(pg['released'] and away)
  valid=(all(pg.values()) and loaded and np.all(j[7:]>.030) and np.all(finger<.01) and away and m['overlap_m']<=s.penetration_tolerance_m)
  if valid:
   if self.stable_anchor is None:self.stable_anchor=(p,np.array(m['orientation']));self.stable_start=t
   delta=np.linalg.norm(p-self.stable_anchor[0]);angle=2*np.arccos(np.clip(abs(np.dot(self.stable_anchor[1],m['orientation'])),0,1))
   if delta>s.stable_translation_m or angle>np.radians(s.stable_rotation_deg):self.stable_anchor=(p,np.array(m['orientation']));self.stable_start=t
   self.stable_seconds=t-self.stable_start
  else:self.stable_anchor=None;self.stable_start=None;self.stable_seconds=0.
  if not np.isfinite(np.r_[p,m['orientation'],tcp,j,finger,m['environment_contact_N']]).all():return 'PHYSICS_INVALID','nonfinite_state'
  if m['overlap_m']>s.penetration_tolerance_m:return 'PHYSICS_INVALID','geometric_overlap_'+m['overlap_collider']
  if p[2]<cfg.layout.table_top_m-h/2:return 'DROPPED','below_table'
  if self.stable_seconds+1e-9>=s.stable_seconds:return 'SUCCESS','correct_object_extracted_transported_loaded_released_retreated_stable'
  # No phase or commanded depth can make the episode successful.
  if not pg['correct_source']:return 'WRONG_OBJECT','initial_object_or_slot_mismatch'
  if t>9 and not pg['extracted']:
   return ('EXTRACTION_BLOCKED','bilateral_grasp_but_not_clear_of_rack') if pg['grasp'] else ('GRASP_FAILURE','bilateral_contact_or_extraction_missing')
  if pg['transported'] and not pg['arrived'] and m['environment_contact_N']>2.:return 'TRANSPORT_COLLISION','unexpected_contact_during_actual_transport'
  if pg['transported'] and not pg['released'] and p[2]<cfg.layout.chamber_floor_z_m-h/2-.005:return 'DROPPED','transport_drop'
  if t>=s.timeout_s:
   if not pg['grasp']:return 'GRASP_FAILURE','bilateral_grasp_missing'
   if not pg['extracted']:return 'EXTRACTION_BLOCKED','not_clear_of_source'
   if not pg['inserted']:return 'INSERTION_BLOCKED','actual_depth_or_orientation_shortfall'
   if not pg['released'] or not pg['retreated']:return 'TIMEOUT','release_or_retreat_not_completed'
   return 'UNSTABLE_AFTER_RELEASE','not_independently_stable'
  return 'RUNNING',''
