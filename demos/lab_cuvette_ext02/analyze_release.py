"""Read original ext01 trajectory, derive geometry/rotation; never change it."""
from pathlib import Path
import json,numpy as np,trimesh
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_ext02.build import ROOT,source_mesh
from demos.lab_cuvette_external.run import write

def analyze():
 out=ROOT/'outputs/lab_cuvette_loading/V0_ext02';doc=ROOT/'docs/lab_cuvette_loading/V0_ext02';doc.mkdir(exist_ok=True)
 rows=json.load(open(ROOT/'outputs/lab_cuvette_loading/V0_ext01/grasp_table02/physics_records.json'));t=np.array([r['time'] for r in rows]);p=np.array([r['position'] for r in rows]);q=np.array([r['orientation'] for r in rows]);rot=Rotation.from_quat(np.c_[q[:,1:],q[:,0]]);m=source_mesh();bottom=np.array([(m.vertices@r[2]+pos[2]).min() for r,pos in zip(rot.as_matrix(),p)]);tilt=np.degrees(np.arccos(np.clip(rot.as_matrix()[:,2,2],-1,1)));f=np.array([r['finger_force_N'] for r in rows]);support=np.array([sum(abs(x) for x in r['contact_force_N']) for r in rows]);speed=np.linalg.norm(np.array([r['linear_velocity'] for r in rows]),axis=1);omega=np.r_[0.,np.linalg.norm((rot[1:]*rot[:-1].inv()).as_rotvec(),axis=1)/np.diff(t)]
 def at(mask):
  ids=np.flatnonzero(mask)
  if not len(ids):return None
  i=ids[0];return dict(time_s=float(t[i]),phase=rows[i]['phase'],source_bottom_z_m=float(bottom[i]),bottom_gap_m=float(bottom[i]-.74),tilt_deg=float(tilt[i]),finger_contact_N=f[i],environment_scalar_contact_sum_N=float(support[i]),linear_speed_m_s=float(speed[i]),derived_angular_speed_rad_s=float(omega[i]))
 report=dict(source='V0_ext01/grasp_table02 original physics_records, no rerun',open_begin=at(np.array([r['phase']=='OPEN' for r in rows])),first_bilateral_contact_loss_after_open=at((t>22)&(f.min(1)<.02)),right_contact_near_withdrawal_onset=at((t>24)&(f[:,1]>.02)),first_both_clear_after_retreat=at((t>24)&(f.max(1)<.01)),first_tilt_2deg_after_open=at((t>22)&(tilt>2)),first_tilt_10deg_after_open=at((t>22)&(tilt>10)),first_tilt_45deg_after_open=at((t>22)&(tilt>45)),first_table_like_environment_impact=at((t>22)&(support>.01)),final=at(t>=t[-1]),missing_original_fields=['angular_velocity (derived from quaternions instead)','per-contact collider path / force vector direction','commanded finger targets at physics rate'],causal_scope='unsupported opening and residual unilateral contact directly observed; inherited robot/collision dynamics not independently isolated as causes')
 write(out/'old_release_analysis.json',report)
 footprint=m.vertices[m.vertices[:,2]<1e-8,:2];ch=ConvexHull(footprint);com=np.array([8.9723807e-7,9.038207e-7,.029027632]);margin=-(ch.equations[:,:2]@com[:2]+ch.equations[:,2]).max();write(out/'source_support_geometry.json',dict(source_dimensions_m=m.extents,lowest_z_m=float(m.vertices[:,2].min()),support_vertices_z_tolerance_m=1e-8,footprint_vertices_m=footprint[ch.vertices],uniform_mass_com_m=com,com_projection_inside=bool(margin>0),minimum_convex_footprint_margin_m=float(margin),scope='upright on horizontal plane; convex source footprint; assumed uniform mass, not measured COM'))
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(4,1,figsize=(10,10),sharex=True)
 axes[0].plot(t,(bottom-.74)*1000);axes[0].axhline(0,color='black',lw=.8);axes[0].set_ylabel('Source bottom\nabove table (mm)')
 axes[1].plot(t,tilt);axes[1].set_ylabel('Tilt (deg)')
 axes[2].plot(t,f[:,0],label='left');axes[2].plot(t,f[:,1],label='right');axes[2].plot(t,support,label='environment scalar sum');axes[2].set_ylabel('Contact (N)');axes[2].legend()
 axes[3].plot(t,speed,label='linear m/s');axes[3].plot(t,omega,label='derived angular rad/s');axes[3].legend();axes[3].set_xlabel('Simulation time (s)')
 for ax in axes:ax.set_xlim(21,28.5);ax.axvline(22,color='red',ls='--');ax.axvline(24,color='orange',ls='--');ax.grid(alpha=.2)
 fig.suptitle('Original ext01 release: OPEN ~22s, withdrawal ~24s; no lower-to-support phase');fig.tight_layout();fig.savefig(doc/'old_release_alignment.png',dpi=160)
 print(json.dumps(report,default=lambda a:a.tolist() if hasattr(a,'tolist') else str(a),indent=2))
if __name__=='__main__':analyze()
