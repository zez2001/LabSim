"""Read-only source mesh inspection; explicit source-world to metre/Z-up transforms."""
from pathlib import Path
import json, hashlib
import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdShade, UsdPhysics

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'assets/lab_cuvette_loading/V0_ext01/source'
DOC=ROOT/'docs/lab_cuvette_loading/V0_ext01'
CANDIDATES=['/RotatedRoot/newnew4/newnew4/tn__2_ZBFi3j3','/RotatedRoot/newnew4/newnew4/tn__2_1_dNPo5b5']

def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x))+'\n')

def mesh_records(filename,source_dir=SOURCE):
    stage=Usd.Stage.Open(str(Path(source_dir)/filename));cache=UsdGeom.XformCache();rows=[]
    for prim in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh):continue
        mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),dtype=float)
        matrix=np.array(cache.GetLocalToWorldTransform(prim));world=(np.c_[points,np.ones(len(points))]@matrix)[:,:3]
        faces=[];indices=np.array(mesh.GetFaceVertexIndicesAttr().Get());start=0
        for n in mesh.GetFaceVertexCountsAttr().Get():
            ids=indices[start:start+n];faces.extend([ids[[0,i,i+1]] for i in range(1,n-1)]);start+=n
        bound,rel=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        rows.append(dict(path=str(prim.GetPath()),points=world,faces=np.array(faces),local_to_source_world_row_matrix=matrix,instance_proxy=prim.IsInstanceProxy(),material=str(bound.GetPath()) if bound else None,subsets=[str(c.GetPath()) for c in prim.GetChildren() if c.IsA(UsdGeom.Subset)]))
    return stage,rows

def normalized(filename,source_dir=SOURCE):
    stage,rows=mesh_records(filename,source_dir);points=np.concatenate([r['points'] for r in rows]);unit=UsdGeom.GetStageMetersPerUnit(stage)
    # Instrument source-world points already include RotatedRoot's +90 deg X.
    up=str(UsdGeom.GetStageUpAxis(stage))
    if up not in ['Y','Z']:raise ValueError('Unsupported source upAxis; explicit conversion required')
    R=np.eye(3) if up=='Z' else np.array([[1,0,0],[0,0,-1],[0,1,0.]])
    rotated=points@R.T*unit;lo=rotated.min(0);hi=rotated.max(0);origin=np.r_[(lo[:2]+hi[:2])/2,lo[2]]
    T=np.eye(4);T[:3,:3]=R.T*unit;T[3,:3]=-origin
    for row in rows:row['vertices_m']=(np.c_[row['points'],np.ones(len(row['points']))]@T)[:,:3]
    info=dict(filename=filename,meters_per_unit=float(unit),up_axis=str(UsdGeom.GetStageUpAxis(stage)),default_prim=str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,source_world_min=points.min(0),source_world_max=points.max(0),normalized_min=lo-origin,normalized_max=hi-origin,dimensions_m=hi-lo,source_world_to_normalized_row_matrix=T,origin_definition='XY AABB centre and lowest actual transformed vertex; NOT centre of mass',external_references=list(stage.GetRootLayer().GetExternalReferences()),custom_layer_data=stage.GetRootLayer().customLayerData,ordinary_traverse_meshes=sum(p.IsA(UsdGeom.Mesh) for p in stage.Traverse()),instance_proxy_meshes=len(rows),instances=[dict(path=str(p.GetPath()),prototype=str(p.GetPrototype().GetPath())) for p in stage.Traverse() if p.IsInstance()],physics_prims=[str(p.GetPath()) for p in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.CollisionAPI) or p.HasAPI(UsdPhysics.MassAPI)])
    return info,rows

def tri(row):return trimesh.Trimesh(vertices=row['vertices_m'],faces=row['faces'],process=True,validate=True)

def clipped_hull(mesh,planes):
    """Clip source triangles, then hull one small region; no optional polygon packages."""
    polygons=mesh.triangles.copy()
    for origin,normal in planes:
        kept=[];origin=np.asarray(origin);normal=np.asarray(normal)
        for polygon in polygons:
            distances=(polygon-origin)@normal;out=[]
            for a,b,da,db in zip(polygon,np.roll(polygon,-1,axis=0),distances,np.roll(distances,-1)):
                if da>=-1e-12:out.append(a)
                if (da>0 and db<0) or (da<0 and db>0):out.append(a+(b-a)*da/(da-db))
            if len(out)>=3:kept.append(np.asarray(out))
        polygons=kept
    vertices=np.unique(np.round(np.concatenate(polygons),12),axis=0)
    return trimesh.convex.convex_hull(vertices)

def radial_hulls(mesh,count=32):
    # The actual source inner floor is measured by a centre ray, not guessed
    # from the old V0 bottom thickness. Bottom cap is convex; walls are clipped
    # into angular wedges so their hulls cannot bridge the entire cavity.
    points,_,_=mesh.ray.intersects_location([[0,0,mesh.bounds[1,2]+.001]],[[0,0,-1]],multiple_hits=True)
    floor=float(points[:,2].max());parts=[clipped_hull(mesh,[([0,0,floor],[0,0,-1])])]
    # Add height bands at source fillet transitions rather than a hull bridging
    # the full concave rim/bottom fillets. Values are derived from source vertices.
    heights=np.unique(mesh.vertices[:,2]);low=heights[(heights>floor+1e-6)&(heights<floor+.001)].max()+1e-7
    high=heights[(heights>mesh.bounds[1,2]-.001)&(heights<mesh.bounds[1,2]-1e-6)].min()-1e-7
    bands=[floor+1e-7,low,high,mesh.bounds[1,2]]
    for z0,z1 in zip(bands[:-1],bands[1:]):
        for i in range(count):
            a=i*2*np.pi/count;b=(i+1)*2*np.pi/count
            # Exclude coplanar floor triangles, which would bridge the cavity.
            parts.append(clipped_hull(mesh,[([0,0,z0],[0,0,1]),([0,0,z1],[0,0,-1]),([0,0,0],[-np.sin(a),np.cos(a),0]),([0,0,0],[np.sin(b),-np.cos(b),0])]))
    return floor,parts

def inspect():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    infos={};meshes={}
    for name in ['newnew4.usd','TestTube_Baked.usd']:
        info,rows=normalized(name);summary=[]
        for row in rows:
            m=tri(row);summary.append({k:v for k,v in row.items() if k not in ['points','faces','vertices_m']})
            summary[-1].update(vertices=len(row['vertices_m']),triangles=len(row['faces']),bounds_m=m.bounds,dimensions_m=m.extents,watertight=m.is_watertight,winding_consistent=m.is_winding_consistent,euler_number=m.euler_number,volume_m3=m.volume,merged_vertices=len(m.vertices),components=len(m.split(only_watertight=False)))
        info['meshes']=summary;infos[name]=info;meshes[name]=rows
    vessel=tri(meshes['TestTube_Baked.usd'][0]);obj=trimesh.load(SOURCE/'试管/试管.obj',force='mesh',process=False)
    src=meshes['TestTube_Baked.usd'][0]['points'];infos['obj_comparison']=dict(usd_vertices=len(src),obj_vertices=len(obj.vertices),nearest_vertex_max_m=float(__import__('scipy').spatial.cKDTree(obj.vertices).query(src)[0].max()))
    fig,axs=plt.subplots(2,3,figsize=(15,9))
    for ax,z in zip(axs[0],[.001,.020,.060]):
        seg=trimesh.intersections.mesh_plane(vessel,[0,0,1],[0,0,z])
        for s in seg:ax.plot(s[:,0]*1000,s[:,1]*1000,'k-',lw=.7)
        ax.set_title(f'Vessel horizontal section z={z*1000:.1f} mm');ax.set_aspect('equal');ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.grid(alpha=.2)
    seats=[]
    for ci,path in enumerate(CANDIDATES):
        row=next(r for r in meshes['newnew4.usd'] if r['path'].startswith(path+'/'));m=tri(row);b=m.bounds;centre=b.mean(0);seats.append(dict(path=path,bounds_m=b,dimensions_m=m.extents,identity='candidate only; unconfirmed instrument loading role'))
        ax=axs[1,ci]
        for z,colour in zip(np.linspace(b[0,2]+.0002,b[1,2]-.0002,5),['k','r','g','b','m']):
            for s in trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,z]):ax.plot((s[:,0]-centre[0])*1000,(s[:,1]-centre[1])*1000,color=colour,lw=.7)
        ax.set_title(f'Candidate {ci+1}: 5 Z sections; original scale');ax.set_aspect('equal');ax.set_xlabel('local X mm');ax.set_ylabel('local Y mm');ax.grid(alpha=.2)
    ax=axs[1,2];r=meshes['newnew4.usd'];v=np.concatenate([x['vertices_m'] for x in r]);ax.scatter(v[:,1]*1000,v[:,2]*1000,s=.1,c='gray')
    for s in seats:bb=np.array(s['bounds_m']);ax.plot([bb[0,1]*1000,bb[1,1]*1000],[bb.mean(0)[2]*1000]*2,'r-',lw=3)
    ax.set_title('Instrument side projection; red candidate seats');ax.set_xlabel('Y mm');ax.set_ylabel('Z mm');ax.set_aspect('equal')
    fig.tight_layout();fig.savefig(DOC/'source_sections.png',dpi=180);plt.close(fig)
    infos['candidate_seats']=seats;write(DOC/'source_geometry.json',infos)
    print(json.dumps(infos,ensure_ascii=False,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x),indent=2))

if __name__=='__main__':inspect()
