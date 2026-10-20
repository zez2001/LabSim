"""Zero-task-step camera inspection and composed-stage population checks."""
import hashlib
import numpy as np
from demos.lab_cuvette_external.geometry import write

def save_review(ctx,cameras,cfg,output):
    import cv2
    from pxr import UsdGeom,UsdPhysics,Gf
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    world,stage=ctx['world'],ctx['stage'];d=ctx['fixtures']
    shots={}
    views=[('overview',cameras['wide']),('chamber',cameras['close'])]
    for name,eye,target in [('top',[.20,-.03,2.5],[.20,-.03,.74]),('source',[.20,-.55,1.10],d['source_floor']+[0,0,.025])]:
        c=Camera('/World/Review_'+name,name='review_'+name,frequency=60,resolution=(1280,960));c.set_focal_length(1.5 if name=='top' else 2.5);c.set_clipping_range(.0001,10);set_camera_view(eye=np.array(eye),target=np.array(target),camera_prim_path='/World/Review_'+name);c.initialize();views.append((name,c))
    for _ in range(30):world.render()
    for name,c in views:
        frame=cv2.cvtColor(c.get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR)
        for i,label in enumerate(['V0_demo04 | SINGLE INSTRUMENT | ORIGINAL A/B RETAINED',f'Root yaw {d["instrument_yaw_deg"]:.3f}deg | vessel12.5x12.5x67.5mm USER NOMINAL','RESET PREVIEW: no task physics steps; full native insertion GEOMETRY BLOCKED']):
            cv2.putText(frame,label,(12,26+i*27),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,0,0),3);cv2.putText(frame,label,(12,26+i*27),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1)
        path=output/(name+'.png');cv2.imwrite(str(path),frame);shots[name]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    stage.Flatten().Export(str(output/'scene.usda'))
    prims=list(stage.Traverse());colliders=[str(p.GetPath()) for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
    visual=[p for p in prims if str(p.GetPath()).startswith('/World/Instrument/Visual/') and p.IsA(UsdGeom.Mesh)]
    original_A=stage.GetPrimAtPath('/World/Instrument/Collision/SourceMesh3');original_B=stage.GetPrimAtPath('/World/Instrument/Collision/SourceMesh4')
    checks=dict(exactly_one_instrument=(bool(stage.GetPrimAtPath('/World/Instrument')) and not bool(stage.GetPrimAtPath('/World/NeighborInstrument'))),all_original_instrument_colliders=len([p for p in colliders if p.startswith('/World/Instrument/')])==8,original_A_active=bool(original_A) and original_A.IsActive(),original_B_active=bool(original_B) and original_B.IsActive(),no_engineering_adapter=not bool(stage.GetPrimAtPath('/World/Instrument/EngineeringAdapterA')),rack36slots=len(list(stage.GetPrimAtPath('/World/SourceRack/Slots').GetChildren()))==36,rack50colliders=len([p for p in colliders if p.startswith('/World/SourceRack/')])==50,cuvette28colliders=len([p for p in colliders if p.startswith('/World/Cuvette/')])==28,opening_faces_rack=float(d['opening_direction_world'][:2]@((d['rack_origin']-d['instrument_origin'])[:2]/np.linalg.norm((d['rack_origin']-d['instrument_origin'])[:2])))>.99999,reset_position_check=max(ctx['errors'])<1e-6)
    result=dict(version='V0_demo04',task_physics_steps=0,static_scene_pass=all(checks.values()),checks=checks,layout=d,colliders=colliders,screenshots=shots,scene_usd_sha256=hashlib.sha256((output/'scene.usda').read_bytes()).hexdigest(),source_rack_tentative=True,nominal_dimensions_source='user supplied',full_task_executed=False,workflow_success=False,native_pair_success=False,real_calibrated=False)
    write(output/'static_validation.json',result);print('STATIC_SCENE',result['static_scene_pass'],checks,flush=True);return result
