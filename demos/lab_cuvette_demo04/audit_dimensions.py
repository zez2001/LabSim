"""Read-only actual-vertex dimension table across source, derived and world frames."""
from pathlib import Path
import argparse,csv,hashlib,json
import numpy as np
from pxr import Usd,UsdGeom
from omegaconf import OmegaConf
from demos.lab_cuvette_external.geometry import ROOT,SOURCE,normalized
from demos.lab_cuvette_demo04.scene import layout

def meshes(path):
    stage=Usd.Stage.Open(str(path),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();out=[]
    for p in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
        if not p.IsA(UsdGeom.Mesh):continue
        v=np.asarray(UsdGeom.Mesh(p).GetPointsAttr().Get(),float)
        v=(np.c_[v,np.ones(len(v))]@np.asarray(cache.GetLocalToWorldTransform(p)))[:,:3]
        out.append((str(p.GetPath()),v))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    cfg=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0_demo04/native_nominal.yaml');d=layout(cfg);rows=[]
    def add(role,frame,points,basis,prim):
        pts=np.asarray(points);extent=np.ptp(pts,axis=0)*1000
        rows.append(dict(role=role,frame=frame,X_mm=extent[0],Y_mm=extent[1],Z_mm=extent[2],basis=basis,prim=prim))
    info,raw=normalized('newnew4.usd')
    # normalized() retains every source instance and applies full unit/up-axis transform.
    from demos.lab_cuvette_external.geometry import tri
    rawv=[tri(r).vertices for r in raw]
    body_index=next(i for i,r in enumerate(raw) if r['path'].endswith('/tn__1_x1ZBa0c2t04z0ZA6/Mesh'))
    add('instrument_body','source_normalized_m',rawv[body_index],'actual transformed original source vertices',raw[body_index]['path'])
    add('open_assembly','source_normalized_m',np.concatenate(rawv),'all8 original source instances; source lid pose','/RotatedRoot')
    all_inst=meshes(ROOT/cfg.asset_directory/'instrument_native.usda');visual=[(n,v) for n,v in all_inst if '/Visual/' in n]
    for role,selected in [('instrument_body',[x for x in visual if x[0].endswith(raw[body_index]['path'].split('/RotatedRoot',1)[1])]),('open_assembly',visual),('selected_A',[x for x in visual if x[0].endswith(raw[3]['path'].split('/RotatedRoot',1)[1])]),('retained_B',[x for x in visual if x[0].endswith(raw[4]['path'].split('/RotatedRoot',1)[1])])]:
        assert selected,(role,[n for n,v in visual])
        v=np.concatenate([v for n,v in selected]);names=';'.join(n for n,v in selected)
        add(role,'derived_instrument_local_m',v,'actual derived vertices; inherited video lid pose',names)
        add(role,'final_world_m',v@d['instrument_rotation'].T+d['instrument_origin'],'world AABB is projected extent after yaw135; not component scale',names)
    vessel=meshes(ROOT/cfg.asset_directory/'vessel_125_mm.usda')
    for role,selected in [('vessel_visual',[v for n,v in vessel if '/Visual/' in n]),('vessel_collision_input_union_bbox',[v for n,v in vessel if '/Collision/' in n])]:
        add(role,'derived_vessel_local_m',np.concatenate(selected),'actual reloaded mesh vertices; not cooked geometry',';'.join(n for n,v in vessel if ('/Visual/' if role=='vessel_visual' else '/Collision/') in n))
    for role,size,basis in [('rack_outer',[.110,.110,.028],'6x6 parametric design unchanged'),('rack_slot',[.016,.016,.025],'unmeasured demo assumptions; base3mm wall2mm'),('vessel_nominal',[.0125,.0125,.0675],'user nominal XY and retained Z'),('seat_central_reference',[.0126,.0126,.029],'central section only; inward tabs retained')]:
        rows.append(dict(role=role,frame='design_nominal',X_mm=size[0]*1000,Y_mm=size[1]*1000,Z_mm=size[2]*1000,basis=basis,prim=''))
    with (a.output/'dimensions.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    sources=[SOURCE/'newnew4.usd',SOURCE/'TestTube_Baked.usd',ROOT/cfg.asset_directory/'instrument_native.usda',ROOT/cfg.asset_directory/'vessel_125_mm.usda',ROOT/'config/lab_cuvette_loading/V0_demo04/native_nominal.yaml']
    (a.output/'provenance.json').write_text(json.dumps(dict(method='actual source/derived vertices with complete USD transforms; final world Rz+translation once',source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},instrument_count=1,units='m internal;mm table',native_cooked_vertices_read=False,real_calibrated=False),indent=2)+'\n')
    print(a.output)
if __name__=='__main__':main()
