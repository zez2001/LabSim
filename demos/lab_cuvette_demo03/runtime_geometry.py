"""Independent authored-source envelope checks in measured world poses.

The full source vertices and its unique edges are clipped at each fixture rim.
This checks upright near-centred placement against the analytic square void,
including edge/plane intersections rather than only vertices below the rim.
It is not a global cooked-PhysX surface or arbitrary-mesh penetration proof.
"""
import numpy as np
from scipy.spatial.transform import Rotation


def clipped_points(vertices, edges, lo, hi):
    selected=[vertices[(vertices[:,2]>=lo)&(vertices[:,2]<=hi)]]
    segments=vertices[edges]
    for z in [lo,hi]:
        dz=segments[:,1,2]-segments[:,0,2]
        valid=(np.abs(dz)>1e-12)&((segments[:,0,2]-z)*(segments[:,1,2]-z)<0)
        e=segments[valid]
        if len(e):selected.append(e[:,0]+((z-e[:,0,2])/(e[:,1,2]-e[:,0,2]))[:,None]*(e[:,1]-e[:,0]))
    return np.concatenate(selected)


def fixture_measure(vertices, edges, origin, rotation, inner, depth):
    local=(vertices-origin)@rotation
    center=(local.min(0)+local.max(0))/2
    # If entirely remote from this fixture its walls and floor cannot touch.
    horizontal=np.max(np.abs(center[:2]))<inner/2+.012
    bottom=float(local[:,2].min())
    samples=clipped_points(local,edges,0.,depth)
    excess=max(0.,float(np.max(np.abs(samples[:,:2]))-inner/2)) if horizontal and len(samples) else 0.
    floor_pen=max(0.,-bottom) if horizontal else 0.
    contained=bool(horizontal and len(samples) and np.max(np.abs(samples[:,:2]))<=inner/2+1e-9)
    return dict(gap=bottom,depth=depth-bottom,inside=contained,penetration=max(excess,floor_pen))


def hand_clearance(link_points, bodies, vessel_vertices):
    """AABB separation lower bound from actual poses of all three gripper links."""
    cup_lo=vessel_vertices.min(0);cup_hi=vessel_vertices.max(0);dist=[]
    for name,vertices in link_points.items():
        p,q=bodies[name].get_world_pose()
        v=Rotation.from_quat(np.r_[q[1:],q[0]]).apply(vertices)+p
        delta=np.maximum(np.maximum(v.min(0)-cup_hi,cup_lo-v.max(0)),0.)
        dist.append(float(np.linalg.norm(delta)))
    return min(dist)
