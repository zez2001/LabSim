exec(open('/tmp/labsim_gpt05_collision_cpu_20261027.py').read().split('native=[];')[0])
x=json.loads((O/'raw_extract.json').read_text());g=json.loads((O/'geometry_extract.json').read_text())
ref=None;grasp=[];first200=None
for line in gzip.open(E/'physics_records.jsonl.gz','rt'):
 d=json.loads(line);t=d['t']
 if abs(t-14.1125)<1e-8:ref=d
 if ref is not None:
  rp=np.array(d['cup_in_hand_position_m']);rr=Rot.from_quat(np.r_[d['cup_in_hand_quaternion_wxyz'][1:],d['cup_in_hand_quaternion_wxyz'][0]])
  p0=np.array(ref['cup_in_hand_position_m']);r0=Rot.from_quat(np.r_[ref['cup_in_hand_quaternion_wxyz'][1:],ref['cup_in_hand_quaternion_wxyz'][0]])
  disp=float(np.linalg.norm(rp-p0));angle=float(np.degrees((rr*r0.inv()).magnitude()));anchor=np.array([0,0,.053]);ad=float(np.linalg.norm(rp+rr.apply(anchor)-(p0+r0.apply(anchor))))
  grasp.append(dict(t=t,body_drift_m=disp,orientation_drift_deg=angle,configured_anchor_drift_m=ad,finger_contact_N=d['finger_contact_N']))
  if disp>.0002 and first200 is None:first200=grasp[-1]
pre=[r for r in grasp if r['t']<x['forbidden'][0]['t']]
result=dict(reference_t=ref['t'],pre_impact_max_body=max(pre,key=lambda x:x['body_drift_m']),pre_impact_max_anchor=max(pre,key=lambda x:x['configured_anchor_drift_m']),first_over_200um=first200,last=grasp[-1])
(O/'grasp_before_after_impact.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
print('TRANSFORM',g['instrument_mesh5']['usd_composed_world_row_matrix'],'APPROX',g['instrument_mesh5']['authored_approximation'])
print('FIRSTSTATE',g['state']);print('SIDEPIXEL',g['offline_side_projection_of_actual_contact'])
