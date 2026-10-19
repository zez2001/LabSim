"""Surface/solid comparisons, compound UNION semantics, deterministic sampling.

All directed distance candidates are outside the destination solid. Thus a
nearest internal compound face cannot create a false exterior mismatch.
These samples are evidence, never a global Hausdorff bound.
"""
from pathlib import Path
import argparse,json
import numpy as np,trimesh
from scipy.spatial import ConvexHull,HalfspaceIntersection
from demos.lab_cuvette_ext02.build import source_mesh,ROOT
from demos.lab_cuvette_external.run import write

EPS=1e-8
def meshes(rows):
    # Native convex polygons may be only approximately planar. A fan from the
    # first vertex then makes a nonconvex, nonplanar triangulated skin. Membership
    # above is defined by convex hull halfspaces, so distance must use the SAME
    # closed convex set, not that arbitrary polygon fan.
    result=[]
    for r in rows:
        if r.get('raw_planes'):
            matrix=np.array(r['local_to_body_row_matrix']);eq=(np.linalg.inv(matrix)@np.array(r['raw_planes']).T).T
            eq/=np.linalg.norm(eq[:,:3],axis=1)[:,None]
            vertices=HalfspaceIntersection(eq,np.array(r['vertices']).mean(0)).intersections
        else:vertices=np.array(r['vertices'])
        result.append(trimesh.convex.convex_hull(vertices))
    return result

class Union:
    def __init__(self,ms):
        self.ms=ms;self.eqs=[ConvexHull(m.vertices).equations for m in ms];self.mesh=trimesh.util.concatenate(ms)
    def contains(self,pts,eps=EPS):
        inside=np.zeros(len(pts),dtype=bool)
        for eq,m in zip(self.eqs,self.ms):
            ids=np.flatnonzero(~inside & np.all((pts>=m.bounds[0]-abs(eps)) & (pts<=m.bounds[1]+abs(eps)),axis=1))
            if len(ids):inside[ids]=np.all(pts[ids]@eq[:,:3].T+eq[:,3]<=eps,axis=1)
        return inside
    def sample(self,n=12000):
        pts=np.concatenate([m.vertices for m in self.ms]+[trimesh.sample.sample_surface(self.mesh,n,seed=8202)[0]])
        # Strictly inside any part = internal overlap face, exclude it.
        return pts[~self.contains(pts,-EPS)]

def distance(mesh,pts):
    if not len(pts):return np.empty((0,3)),np.empty(0),np.empty(0,dtype=int)
    # trimesh's absolute tolerances misclassify Voronoi regions on micrometre
    # triangles in metre coordinates. Numerically condition BOTH operands,
    # then return metres. This changes no asset or physics parameter.
    scale=1000.;conditioned=mesh.copy();conditioned.apply_scale(scale)
    chunks=[]
    for i in range(0,len(pts),256):chunks.append(trimesh.proximity.closest_point(conditioned,pts[i:i+256]*scale))
    result=tuple(np.concatenate([x[k] for x in chunks]) for k in range(3))
    if not np.isfinite(result[1]).all():raise ValueError('Nonfinite point-to-triangle distance; no geometry gate may pass')
    return result[0]/scale,result[1]/scale,result[2]

def directed(pts,dstmesh,dstcontains,srcname,dstname):
    outside=~dstcontains(pts)
    selected=pts[outside]
    if len(selected)==0:return dict(sample_count=len(pts),outside_count=0,observed_max_m=0.,support_observed_max_m=0.,worst=None)
    closest,d,faces=distance(dstmesh,selected);idx=int(d.argmax());bottom=selected[:,2]<=.0003
    support_ids=np.flatnonzero(bottom);si=int(support_ids[d[bottom].argmax()]) if len(support_ids) else None
    def point(i):return dict(point_m=selected[i],nearest_triangle_point_m=closest[i],triangle_index=int(faces[i]),distance_m=float(d[i])) if i is not None else None
    return dict(source=srcname,destination=dstname,sample_count=len(pts),outside_count=int(outside.sum()),outside_beyond_10nm=int((d>EPS).sum()),observed_max_m=float(d[idx]),support_observed_max_m=float(d[bottom].max()) if bottom.any() else 0.,worst=point(idx),worst_support=point(si))

def parity_check(m,pts):
    votes=[]
    for direction in [[1.,.173,.391],[.219,1.,.473],[.291,.137,1.]]:
        locations,ray,tri=m.ray.intersects_location(pts,np.tile(direction,(len(pts),1)),multiple_hits=True)
        votes.append(np.bincount(ray,minlength=len(pts))%2==1)
    return np.array(votes)

def audit(folder):
    out=Path(folder);A=source_mesh();B=Union(meshes(json.loads((out/'B_input.json').read_text())));rawC=json.loads((out/'C_cooking_query.json').read_text());C=Union(meshes(rawC['hulls']))
    ap=np.r_[A.vertices,trimesh.sample.sample_surface(A,18000,seed=8302)[0]];bp=B.sample();cp=C.sample()
    Ac=lambda p:A.contains(p)
    comparisons={}
    for name,ps,mesh,con,sn,dn in [('A_missing_B',ap,B.mesh,B.contains,'A','B'),('B_extra_A',bp,A,Ac,'B','A'),('B_missing_C',bp,C.mesh,C.contains,'B','C'),('C_extra_B',cp,B.mesh,B.contains,'C','B'),('A_missing_C',ap,C.mesh,C.contains,'A','C'),('C_extra_A',cp,A,Ac,'C','A')]:comparisons[name]=directed(ps,mesh,con,sn,dn)
    rng=np.random.default_rng(7900);samples=rng.uniform(A.bounds[0]-.0003,A.bounds[1]+.0003,(12000,3));actual=A.contains(samples);cu=C.contains(samples,1e-10);bu=B.contains(samples,1e-10);under=actual&~cu;over=cu&~actual
    ids=np.flatnonzero(under);votes=parity_check(A,samples[ids]);valid=np.all(votes,axis=0)
    nearest,depth,face=distance(C.mesh,samples[ids]);write(out/'uncovered_samples.json',dict(definition='uniform seed7900 samples within A material by ray parity and outside geometric union of C halfspaces (<=1e-10 m)',tolerance_m=1e-10,points=samples[ids],source_3_direction_parity=votes,cooked_union_distances_m=depth,points_misclassified_by_parity=int((~valid).sum())))
    gap=directed(samples[over],A,Ac,'C_volume_samples','A')
    # Empty cavity: ray from centre downward gives floor; points strictly above
    # that floor, inside inner XY square, and not in A = declared cavity subset.
    cavity=(samples[:,2]>.004884)&(np.abs(samples[:,0])<.00625)&(np.abs(samples[:,1])<.00625)&~actual
    result=dict(frames='metres, bottom-centred Z-up BODY frame; local mesh transforms explicitly composed once in support.py at recorded t=0',comparisons=comparisons,uniform_volume_samples=12000,missing_count=int(under.sum()),missing_agree_3_directions=int(valid.sum()),B_missing_count=int((actual&~bu).sum()),extra_count=int(over.sum()),volume_overreach=gap,cavity_subset_extra_B=int((cavity&bu).sum()),cavity_subset_extra_C=int((cavity&cu).sum()),A_bounds=A.bounds,B_bounds=B.mesh.bounds,C_bounds=C.mesh.bounds,shape_counts=dict(B=len(B.ms),C=len(C.ms)),observed_support_error_m=max(comparisons['A_missing_C']['support_observed_max_m'],comparisons['C_extra_A']['support_observed_max_m']),global_bound=False,numerical_epsilon_m=EPS)
    result['C_evidence_scope']='cooking-query representation, NOT complete native actor shape export; see live-ray discrepancy and runtime shape count. No full exclusion of native penetration.'
    result['cavity_subset_points_extra_C_m']=samples[cavity&cu]
    for label,entry in comparisons.items():
        for key in ['worst','worst_support']:
            pt=entry.get(key)
            if pt:
                group=C if label.startswith('C_') else B if label.startswith('B_') else None
                if group:
                    pt['source_shape_indices']=[i for i,eq in enumerate(group.eqs) if np.all(np.array(pt['point_m'])@eq[:,:3].T+eq[:,3]<=1e-7)]
                destination=label.split('_')[-1]
                if destination in ['B','C']:
                    target=B if destination=='B' else C
                    index=int(np.searchsorted(np.cumsum([len(m.faces) for m in target.ms]),pt['triangle_index'],side='right'))
                    paths=[r['path'] for r in (json.loads((out/'B_input.json').read_text()) if destination=='B' else rawC['hulls'])]
                    pt['nearest_shape_path']=paths[index]
                else:pt['nearest_shape_path']='normalised source /Asset/Visual/Mesh'
    # Cross-check cooked query surface against actual scene-query ray hits.
    rays=json.loads((out/'live_rays.json').read_text());o=np.array([r['origin'] for r in rays]);dirs=np.array([r['direction'] for r in rays]);errors=[]
    for i,r in enumerate(rays):
        intervals=[]
        for eq in C.eqs:
            a=eq[:,:3]@dirs[i];b=-(eq[:,:3]@o[i]+eq[:,3]);parallel=np.abs(a)<=1e-12
            if np.any(parallel&(b< -1e-10)):continue
            lo=max(0.,max(b[a< -1e-12]/a[a< -1e-12],default=-np.inf));hi=min(b[a>1e-12]/a[a>1e-12],default=np.inf)
            if lo<=hi+1e-10 and lo<=.04:intervals.append(lo)
        if intervals:
            expected=o[i]+dirs[i]*min(intervals);errors.append(dict(ray=i,difference_m=float(np.linalg.norm(expected-np.array(r['hit_body_local']))),expected_m=expected,actual_m=r['hit_body_local'],collider=r['collider']))
    result['actual_ray_vs_cooking']=dict(count=len(errors),max_error_m=max((r['difference_m'] for r in errors),default=None),samples=errors,limitation='sampled outer surfaces; not every native actor face read back')
    write(out/'geometry_audit.json',result)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for ax,z in zip(axes.ravel(),[.00001,.0001,.001,.005,.03,.0674]):
        for obj,color,label in [(A,'black','A source'),(B.mesh,'tab:blue','B input'),(C.mesh,'tab:red','C cooking')]:
            seg=trimesh.intersections.mesh_plane(obj,[0,0,1],[0,0,z])
            # Compound section lines are internal too: expressly labelled here,
            # excluded from numerical surface assessment above.
            for line in seg:ax.plot(line[:,0]*1000,line[:,1]*1000,color=color,lw=.55,alpha=.65)
            ax.plot([],[],color=color,label=label)
        ax.set_title(f'z={z*1000:.3f} mm (raw part sections)');ax.set_aspect('equal');ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(out/'ABC_sections.png',dpi=160);plt.close(fig)
    print(out.name,'support_geometry_mm',result['observed_support_error_m']*1000,'missing',result['missing_count'],'ray_error',result['actual_ray_vs_cooking']['max_error_m'],flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);args=p.parse_args()
    for f in args.folders:audit(f)
