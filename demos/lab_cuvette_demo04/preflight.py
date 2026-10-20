"""Original geometry gate and independently permitted non-inserting diagnostic."""
import json,hashlib
from pathlib import Path
import numpy as np
from demos.lab_cuvette_demo04.scene import ROOT,layout
from demos.lab_cuvette_external.run import write

def inspect(cfg,out=None):
    data=layout(cfg);file=ROOT/'docs/lab_cuvette_loading/V0_demo04/geometry/refined_02/native_fit_audit.json';report=json.loads(file.read_text())
    # Neither a centerline width nor the old16mm adapter qualifies the native pair.
    selected=next(x for x in report['seats'] if x['seat']==('A' if data['target_seat_id']=='candidate_far_hinge' else 'B'))
    pair_pass=not bool(selected['final_pose_witnesses'] or selected['first_observed_path_crossing'])
    front=data['opening_direction_world'][:2];toward=(data['rack_origin']-data['instrument_origin'])[:2];toward/=np.linalg.norm(toward)
    orient=float(front@toward);source_margin=(float(cfg.rack.inner_m)-.0125)/2
    result=dict(version='V0_demo04',scene_mode='native_nominal',instrument_count=1,rack_slots=36,source_slot_id=data['source_slot_id'],target_seat_id=data['target_seat_id'],source_floor=data['source_floor'],target_floor=data['target_floor'],instrument_yaw_deg=data['instrument_yaw_deg'],opening_toward_rack_dot=orient,source_side_clearance_m=source_margin,scene_structure_pass=bool(source_margin>0 and orient>.99),geometry_gate_passed=pair_pass,passed=pair_pass,preinsert_passed=bool(source_margin>0 and orient>.99),native_fit_report=str(file),native_fit_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),diagnostic_bottom_stop_z_m=data['target_rim_z']+float(cfg.control.diagnostic_safe_bottom_above_rim_m),diagnostic_scope='grasp and transport only to rim+1mm, then upward10mm and hold; no insertion/release/native success',limitations=['Native tabs still interfere; full native task is blocked.','Scene-structure gate is not whole-arm collision validation.','Source geometry checks are not cooked PhysX global error bounds.'])
    if out is not None:write(Path(out)/'geometry_preflight.json',result)
    return result


def instrument_triangles(cfg):
    from pxr import Usd,UsdGeom,UsdPhysics
    s=Usd.Stage.Open(str(ROOT/cfg.asset_directory/'instrument_native.usda'),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();d=layout(cfg);records=[]
    for p in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()):
        if not p.IsA(UsdGeom.Mesh) or not p.HasAPI(UsdPhysics.CollisionAPI):continue
        m=UsdGeom.Mesh(p);v=np.asarray(m.GetPointsAttr().Get(),float);v=(np.c_[v,np.ones(len(v))]@np.asarray(cache.GetLocalToWorldTransform(p)))[:,:3];v=v@d['instrument_rotation'].T+d['instrument_origin'];f=np.asarray(m.GetFaceVertexIndicesAttr().Get(),int).reshape(-1,3);records.append(dict(path=str(p.GetPath()),triangles=v[f]))
    return s,records

def _box_hits(records,lo,hi):
    from demos.lab_cuvette_demo03.preflight import _box_hits as base
    return base(records,lo,hi)
