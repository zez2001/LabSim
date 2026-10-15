"""Independent actual-triangle section intersection evidence, not nominal offset labels."""
import numpy as np
import trimesh
from demos.lab_cuvette_external.geometry import DOC,CANDIDATES,normalized,tri,write

def intersects(a,b):
    if not len(a) or not len(b):return []
    # Each pair is a real cross-section boundary segment, not an AABB solid.
    P=a[:,0,None,:2];R=a[:,1,None,:2]-P;Q=b[None,:,0,:2];S=b[None,:,1,:2]-Q
    cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
    den=cross(R,S);valid=np.abs(den)>1e-15;delta=Q-P
    t=np.divide(cross(delta,S),den,out=np.zeros_like(den),where=valid);u=np.divide(cross(delta,R),den,out=np.zeros_like(den),where=valid)
    ii,jj=np.where(valid&(t>=-1e-8)&(t<=1+1e-8)&(u>=-1e-8)&(u<=1+1e-8))
    return (a[ii,0,:2]+t[ii,jj,None]*(a[ii,1,:2]-a[ii,0,:2])).tolist()

def widths(segments):
    out={}
    for axis in [0,1]:
        vals=[]
        for s in segments:
            a,b=s[:,1-axis]
            if (a<=0<b) or (b<=0<a):
                f=-a/(b-a);vals.append(float(s[0,axis]+f*(s[1,axis]-s[0,axis])))
        neg=[v for v in vals if v<0];pos=[v for v in vals if v>0]
        out['XY'[axis]]=min(pos)-max(neg) if neg and pos else None
    return out

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _,vrows=normalized('TestTube_Baked.usd');v=tri(vrows[0]);_,rows=normalized('newnew4.usd');reports=[]
    fig,axs=plt.subplots(2,3,figsize=(15,9))
    for ci,path in enumerate(CANDIDATES):
        m=tri(next(x for x in rows if x['path'].startswith(path+'/')));centre=m.bounds.mean(0);m.apply_translation(-np.r_[centre[:2],0]);lo,hi=m.bounds[:,2];samples=[];witnesses=[]
        # Fixed upright centred pose at a candidate loading depth of 10mm. This is
        # a geometrical path probe, not a physical task or a success criterion.
        bottom=hi-.010
        for z in np.arange(lo+.000125,hi,.00025):
            ss=trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,z]);vv=trimesh.intersections.mesh_plane(v,[0,0,1],[0,0,z-bottom])
            points=intersects(ss,vv);w=widths(ss)
            samples.append(dict(z_instrument_m=float(z),z_above_seat_bottom_m=float(z-lo),central_line_boundary_spacing_m=w,intersection_count=len(points)))
            if points:witnesses.append(dict(z_m=float(z),vessel_bottom_z_m=float(bottom),xy_m=points))
        select=[hi-.0005,hi-.005,lo+.002]
        for j,z in enumerate(select):
            ax=axs[ci,j];ss=trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,z]);vv=trimesh.intersections.mesh_plane(v,[0,0,1],[0,0,z-bottom])
            for s in ss:ax.plot(s[:,0]*1000,s[:,1]*1000,'k-',lw=1)
            for s in vv:ax.plot(s[:,0]*1000,s[:,1]*1000,'r-',lw=1)
            ax.set_title(f'Candidate {ci+1}, z above base={(z-lo)*1000:.2f} mm');ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_aspect('equal');ax.grid(alpha=.2)
        # Witness pose must NOT be labelled successful by any new gate.
        widths_x=[s['central_line_boundary_spacing_m']['X'] for s in samples if s['central_line_boundary_spacing_m']['X'] is not None]
        widths_y=[s['central_line_boundary_spacing_m']['Y'] for s in samples if s['central_line_boundary_spacing_m']['Y'] is not None]
        above=hi+.005;negative_crossings=0
        for sample in samples:
            z=sample['z_instrument_m'];ss=trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,z]);vv=trimesh.intersections.mesh_plane(v,[0,0,1],[0,0,z-above]);negative_crossings+=len(intersects(ss,vv))
        reports.append(dict(candidate_path=path,identity_confirmed=False,approach='Z down, upright, centred; yaw0; no lateral correction',status='geometrically_infeasible_under_declared_pose' if witnesses else 'information_insufficient',probe_bottom_z_m=bottom,section_step_m=.00025,numeric_epsilon_m=1e-7,central_line_min_boundary_spacing_m=dict(X=min(widths_x),Y=min(widths_y)),top_section_boundary_spacing_m=widths(trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,hi-.0005])),nominal_width_conflict_at_top_m=float(v.extents[0]-.012600000381469717),actual_boundary_intersection_witnesses=witnesses,sections=samples,negative_case_uninserted=dict(vessel_bottom_z_m=above,intersections=negative_crossings,outside_seat_height=bool(above>hi),geometric_inserted=False,full_success=False,validation='actual mesh sections and actual placed bottom vs seat top; not a full task scorer test'),limitation='Central line boundary spacing does not classify solid/free space and is NOT a full-depth aperture width. At some heights it crosses bolts or solid base. Boundary crossings prove interference for declared pose; not exhaustive arbitrary tilt/yaw/path search. Open seat meshes prevent reliable closed-volume contains tests.'))
    fig.suptitle('Original geometry: black = candidate seat, red = vessel; no scale adjustment');fig.tight_layout();fig.savefig(DOC/'pairing_sections.png',dpi=180);plt.close(fig)
    rack_width=.015;half=(rack_width-v.extents[:2])/2
    result=dict(version='V0_ext01',calibrated=False,full_task_status='blocked_identity_and_geometry',candidate_pairings=reports,vessel_V0_rack=dict(source='V0 proxy unchanged',inner_width_m=rack_width,vessel_width_m=v.extents[:2],nominal_per_side_clearance_m=half,old_slot_random_half_range_m=.00025,old_random_exceeds_clearance=True,conclusion='nominal centred fit geometrically possible for upright axis-aligned straight walls; approx75um clearance requires cooked collision evidence and true geometry; not validated pairing'),vessel_V0_holder=dict(status='mixed_configuration_NOT_external_instrument_pairing',inner_width_m=.015,nominal_per_side_clearance_m=half,used_as_hidden_target=False),full_task_success_thresholds=None,reason='candidate target identities and matched vessel model unknown; source sections show interference under centred vertical loading; do not inherit V0 scoring or success rate')
    write(DOC/'feasibility.json',result);print('FULL_TASK',result['full_task_status']);print('RACK_CLEARANCE_MM',half*1000)

if __name__=='__main__':main()
