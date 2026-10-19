"""Explicit SYNTHETIC inertia diagnostic, never overwrite the source Franka.

Uniform local mesh-AABB solids at inherited masses, evaluated about inherited
COM with parallel-axis theorem. This is not a manufacturer/calibrated inertia.
"""
import os
import numpy as np
from scipy.spatial.transform import Rotation
from pxr import Usd,UsdGeom,UsdPhysics,Gf
from demos.lab_cuvette_ext02.build import ROOT
from demos.lab_cuvette_external.run import write

def build():
    output=ROOT/'assets/lab_cuvette_loading/V0_ext02/franka_inertia_proxy.usda'
    if output.exists():raise FileExistsError(output)
    s=Usd.Stage.CreateNew(str(output));root=UsdGeom.Xform.Define(s,'/Franka');s.SetDefaultPrim(root.GetPrim());UsdGeom.SetStageMetersPerUnit(s,1.);UsdGeom.SetStageUpAxis(s,'Z');root.GetPrim().GetReferences().AddReference(os.path.relpath(ROOT/'assets/robots/Franka.usd',output.parent))
    cache=UsdGeom.XformCache();rows=[]
    for body in list(s.Traverse()):
        if not body.HasAPI(UsdPhysics.RigidBodyAPI):continue
        ma=UsdPhysics.MassAPI(body);mass=ma.GetMassAttr().Get()
        if not mass or mass<=0:continue
        W=np.array(cache.GetLocalToWorldTransform(body));assert np.allclose(np.linalg.svd(W[:3,:3])[1],1), 'Need explicit body-scale handling'
        points=[]
        for p in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
            if not p.IsA(UsdGeom.Mesh):continue
            nearest=p.GetParent()
            while nearest and not nearest.HasAPI(UsdPhysics.RigidBodyAPI):nearest=nearest.GetParent()
            if nearest!=body:continue
            vs=np.array(UsdGeom.Mesh(p).GetPointsAttr().Get());M=np.array(cache.GetLocalToWorldTransform(p))@np.linalg.inv(W);points.extend((np.c_[vs,np.ones(len(vs))]@M)[:,:3])
        if not points:rows.append(dict(path=str(body.GetPath()),status='unchanged_no_mesh'));continue
        points=np.array(points);lo=points.min(0);hi=points.max(0);size=hi-lo;centroid=(hi+lo)/2;com=np.array(ma.GetCenterOfMassAttr().Get());delta=centroid-com
        I=np.diag(mass/12*np.array([size[1]**2+size[2]**2,size[0]**2+size[2]**2,size[0]**2+size[1]**2]))+mass*(delta@delta*np.eye(3)-np.outer(delta,delta))
        vals,axes=np.linalg.eigh(I)
        if np.linalg.det(axes)<0:axes[:,0]*=-1
        quat=Rotation.from_matrix(axes).as_quat();old=ma.GetDiagonalInertiaAttr().Get();ma.CreateDiagonalInertiaAttr(Gf.Vec3f(*vals));ma.CreatePrincipalAxesAttr(Gf.Quatf(float(quat[3]),Gf.Vec3f(*quat[:3])))
        rows.append(dict(path=str(body.GetPath()),mass_kg=mass,COM_unchanged_m=com,bounds_m=[lo,hi],source_diagonal_inertia=old,synthetic_tensor_kg_m2=I,synthetic_principal_inertia_kg_m2=vals,principal_axes_wxyz=np.r_[quat[3],quat[:3]],assumption='uniform mass over source mesh local AABB; parallel-axis shift to unchanged source COM; not calibrated'))
    s.GetRootLayer().Save();write(ROOT/'docs/lab_cuvette_loading/V0_ext02/robot_inertia_proxy.json',dict(source='assets/robots/Franka.usd',visuals_and_collisions_unchanged=True,masses_and_COMs_unchanged=True,inertias=rows,calibrated=False,main_source_robot_success_claim=False))
    print('INERTIA_PROXY',output,'bodies',len(rows))

if __name__=='__main__':build()
