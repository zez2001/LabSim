"""Compare native velocity readback with motion derived from recorded COM poses.
The derived values diagnose inconsistency; they NEVER replace acceptance limits.
"""
from pathlib import Path
import json,numpy as np
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_ext02.build import ROOT
from demos.lab_cuvette_external.run import write

def main():
 base=ROOT/'outputs/lab_cuvette_loading/V0_ext02';results=[]
 for p in sorted(base.glob('table*/trial_*/physics_records.json')):
  rows=json.load(open(p));t=np.array([x['t'] for x in rows]);q=np.array([x['quaternion'] for x in rows]);rot=Rotation.from_quat(np.c_[q[:,1:],q[:,0]]);pos=np.array([x['position'] for x in rows]);com=pos+rot.apply(np.array([8.9723807e-7,9.038207e-7,.029027632]));dt=np.diff(t);vf=np.diff(com,axis=0)/dt[:,None];wf=(rot[1:]*rot[:-1].inv()).as_rotvec()/dt[:,None];v=np.array([x['linear_velocity'] for x in rows[1:]]);w=np.array([x['angular_velocity'] for x in rows[1:]]);mask=t[1:]>=t[-1]-3
  result=dict(run=str(p.parent.relative_to(base)),native_v_rms_m_s=float(np.sqrt(np.mean(np.sum(v[mask]**2,axis=1)))),derived_COM_v_rms_m_s=float(np.sqrt(np.mean(np.sum(vf[mask]**2,axis=1)))),native_w_rms_rad_s=float(np.sqrt(np.mean(np.sum(w[mask]**2,axis=1)))),derived_w_rms_rad_s=float(np.sqrt(np.mean(np.sum(wf[mask]**2,axis=1)))),note='backward pose difference and end-step native readback are distinct measurements; discrepancy observed, mechanism unconfirmed; acceptance unchanged')
  results.append(result);write(p.parent/'velocity_consistency.json',result)
 write(base/'velocity_consistency_summary.json',results)
 selected=base/'table_final_repro01/trial_00/physics_records.json'
 if selected.exists():
  rows=json.load(open(selected));t=np.array([r['t'] for r in rows]);v=np.linalg.norm([r['linear_velocity'] for r in rows],axis=1);w=np.linalg.norm([r['angular_velocity'] for r in rows],axis=1);force=np.array([r['support_force_vector_N'][2] for r in rows]);f=np.array([r['finger_force_N'] for r in rows]);bottom=np.array([r['source_bottom_z_m'] for r in rows])
  import matplotlib;matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  fig,ax=plt.subplots(4,1,figsize=(10,10),sharex=True)
  ax[0].plot(t,(bottom-.74)*1000);ax[0].set_ylabel('Source bottom\nabove table (mm)')
  ax[1].plot(t,v,label='native linear');ax[1].axhline(.001,color='black',ls='--');ax[1].set_ylabel('Native speed (m/s)')
  ax[2].plot(t,w);ax[2].axhline(.02,color='black',ls='--');ax[2].set_ylabel('Native angular\nspeed (rad/s)')
  ax[3].plot(t,force,label='table support');ax[3].plot(t,f[:,0],label='left finger');ax[3].plot(t,f[:,1],label='right finger');ax[3].legend();ax[3].set_ylabel('Contact (N)');ax[3].set_xlabel('Recorded simulation time (s)')
  for a in ax:a.set_xlim(30,38);a.grid(alpha=.2)
  fig.suptitle('Final frozen reproduction: placement support check fails; OPEN never executed');fig.tight_layout();fig.savefig(ROOT/'docs/lab_cuvette_loading/V0_ext02/final_placement_gate.png',dpi=160)
 print('VELOCITY_AUDIT',len(results),'traces')
if __name__=='__main__':main()
