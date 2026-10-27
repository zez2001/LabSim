"""Robot-only FK from public joint values/TCP and a small locked numeric model.

No Isaac, environment, object, collision-query or network dependency. World base
is reconstructed from the measured public TCP, not read from task state. Local
boxes describe authored robot input material only, never scene clearance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_MODEL=ROOT/'config/lab_cuvette_loading/Project_v1_1/robot_self/franka_nominal_kinematics.json'
SOURCE_URDF_SHA256='e9024642e7952cbcaec0ae14425bf1cd19d674d3c98eeef3793913f63a8101b6'
SOURCE_BOXES_SHA256='5f3ff56c2b011c9db69b48bd4e3d2637863f75342e495ab51c740f674f293466'
MODEL_SHA256='8fa2321de1ae537da1276484869cd66ae4f19d374d58c99f84f23a940227fe10'
MODEL_CONTENT_SHA256='81275b520466ee0ad23fc21755959282a1c481f87103414538228dce2e13d7f7'
FRAMES=('panda_link6','panda_link7','panda_hand')
VERSION='Project_v1_1.public_robot_self_kinematics.v1'


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _vector(value,size):
    if not isinstance(value,(list,tuple,np.ndarray)) or len(value)!=size:
        raise ValueError('Wrong robot vector shape')
    if any(isinstance(x,(bool,np.bool_)) or not isinstance(x,(int,float,np.integer,np.floating)) or not math.isfinite(x) for x in value):
        raise ValueError('Nonfinite/nonnumeric robot value')
    return np.asarray(value,dtype=float)


def _rpy(value):
    r,p,y=_vector(value,3);cr,sr=math.cos(r),math.sin(r);cp,sp=math.cos(p),math.sin(p);cy,sy=math.cos(y),math.sin(y)
    return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
        [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])


def _quat_matrix(value):
    q=_vector(value,4);norm=float(np.linalg.norm(q))
    if abs(norm-1)>1e-5:raise ValueError('Public TCP quaternion must be unit wxyz')
    w,x,y,z=q/norm
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def _matrix_quat(r):
    # Largest diagonal branch is stable at pi, including hand->TCP Rz(pi).
    t=float(np.trace(r))
    if t>0:
        s=2*math.sqrt(t+1);q=np.array([s/4,(r[2,1]-r[1,2])/s,(r[0,2]-r[2,0])/s,(r[1,0]-r[0,1])/s])
    else:
        i=int(np.argmax(np.diag(r)));j=(i+1)%3;k=(i+2)%3;s=2*math.sqrt(max(0.,1+r[i,i]-r[j,j]-r[k,k]))
        q=np.zeros(4);q[0]=(r[k,j]-r[j,k])/s;q[i+1]=s/4;q[j+1]=(r[j,i]+r[i,j])/s;q[k+1]=(r[k,i]+r[i,k])/s
    q/=np.linalg.norm(q)
    if q[0]<0:q=-q
    return q


def _pose(position,quaternion):
    result=np.eye(4);result[:3,3]=_vector(position,3);result[:3,:3]=_quat_matrix(quaternion);return result


def load_model(path=DEFAULT_MODEL,*,expected_sha256=MODEL_SHA256):
    path=Path(path)
    if _sha(path)!=expected_sha256:raise ValueError('Locked numeric robot model SHA mismatch')
    value=json.loads(path.read_text())
    if (value.get('source_URDF_SHA256')!=SOURCE_URDF_SHA256 or
            value.get('source_robot_boxes_SHA256')!=SOURCE_BOXES_SHA256 or
            value.get('units')!='m' or value.get('angle_units')!='rad' or
            value.get('joint_order')!=[f'panda_joint{i}' for i in range(1,8)] or
            value.get('selected_frames')!=list(FRAMES)):
        raise ValueError('Invalid numeric robot model contract')
    if hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=MODEL_CONTENT_SHA256:
        raise ValueError('Numeric model content mismatch')
    return value


def forward_local(q_arm,model):
    """Nominal base_link-from-link transforms; never consumes world/task data."""
    q=_vector(q_arm,7);values=dict(zip(model['joint_order'],q));poses={model['base_frame']:np.eye(4)}
    for joint in model['joints']:
        transform=np.eye(4);transform[:3,:3]=_rpy(joint['origin_rpy_rad']);transform[:3,3]=_vector(joint['origin_xyz_m'],3)
        if joint['type']=='revolute':
            angle=values[joint['name']]
            if not joint['lower_rad']-1e-6<=angle<=joint['upper_rad']+1e-6:raise ValueError('Public joint outside declared limits')
            axis=_vector(joint['axis'],3)
            if not np.allclose(axis,[0,0,1],atol=1e-12,rtol=0):raise ValueError('Unsupported locked joint axis')
            motion=np.eye(4);motion[:3,:3]=_rpy([0,0,float(angle)]);transform=transform@motion
        elif joint['type']!='fixed':raise ValueError('Unsupported robot joint type')
        poses[joint['child']]=poses[joint['parent']]@transform
    return poses


def derive_robot_self_state(q_arm,actual_tcp,*,episode_id,observation_id,simulation_time,model=None):
    """Public q7 + public actual world TCP -> nominal robot-own world frames.

    It deliberately accepts no environment or object argument. TCP anchoring
    absorbs public world-base placement; it does not independently calibrate FK.
    """
    if not all(isinstance(v,str) and v for v in (episode_id,observation_id)):
        raise ValueError('Missing public robot identity')
    if isinstance(simulation_time,bool) or not isinstance(simulation_time,(int,float)) or not math.isfinite(simulation_time):
        raise ValueError('Invalid public state time')
    model=load_model() if model is None else model
    if hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=MODEL_CONTENT_SHA256:
        raise ValueError('Numeric model content mismatch')
    local=forward_local(q_arm,model)
    tcp=_pose(actual_tcp['position_m'],actual_tcp['quaternion_wxyz'])
    base=tcp@np.linalg.inv(local[model['tcp_frame']])
    hand_to_tcp=np.linalg.inv(local['panda_hand'])@local[model['tcp_frame']]
    expected=np.eye(4);expected[:3,:3]=np.diag([-1.,-1.,1.]);expected[2,3]=.1
    if not np.allclose(hand_to_tcp,expected,atol=1e-10,rtol=0):raise ValueError('Locked hand/TCP calibration mismatch')
    def numbers(v):return [round(float(x),8) for x in v]
    frames={}
    for name in FRAMES:
        world=base@local[name]
        box=model['nominal_authored_local_boxes'].get(name)
        frames[name]=dict(position_m=numbers(world[:3,3]),quaternion_wxyz=numbers(_matrix_quat(world[:3,:3])),
            authored_local_box=None if box is None else copy.deepcopy(box))
    return dict(schema=VERSION,episode_id=episode_id,observation_id=observation_id,
        simulation_time_s=simulation_time,source='Public measured q7 and actual TCP, locked nominal robot model only',
        coordinate_frame='world',units='m',quaternion_order='wxyz',joint_order=model['joint_order'],
        numeric_model_SHA256=MODEL_SHA256,URDF_SHA256=SOURCE_URDF_SHA256,
        robot_input_asset_SHA256=model['robot_input_asset_SHA256'],frames=frames,
        hand_to_TCP=dict(translation_m=[0,0,.1],quaternion_wxyz=[0,0,0,1]),
        scope='Robot-only nominal FK/INPUT local boxes; hand box excludes fingers and held vessel. Not cooked shape, swept volume, obstacle/seat/object state, clearance, support or safety certification.',
        real_calibrated=False,cooked_shape_verified=False,obstacle_or_held_object_state_included=False,
        numeric_rounding_decimals=8)


def generate_numeric_model(urdf,boxes):
    """Offline recipe. Runtime load_model never requires URDF/USD/LFS files."""
    if _sha(urdf)!=SOURCE_URDF_SHA256 or _sha(boxes)!=SOURCE_BOXES_SHA256:
        raise ValueError('Generation requires locked source bytes')
    root=ET.fromstring(Path(urdf).read_bytes());source={j.find('child').attrib['link']:j for j in root.findall('joint')}
    required=set();base='base_link'
    def chain(link):
        if link==base:return
        joint=source[link];chain(joint.find('parent').attrib['link']);required.add(joint.attrib['name'])
    for name in (*FRAMES,'right_gripper'):chain(name)
    result=[];done={base}
    remaining=[j for j in root.findall('joint') if j.attrib['name'] in required]
    while remaining:
        progress=False
        for j in list(remaining):
            parent=j.find('parent').attrib['link']
            if parent not in done:continue
            origin=j.find('origin');a={} if origin is None else origin.attrib
            row=dict(name=j.attrib['name'],type=j.attrib['type'],parent=parent,child=j.find('child').attrib['link'],
                origin_xyz_m=[float(v) for v in a.get('xyz','0 0 0').split()],
                origin_rpy_rad=[float(v) for v in a.get('rpy','0 0 0').split()])
            if row['type']=='revolute':
                row.update(axis=[float(v) for v in j.find('axis').attrib['xyz'].split()],
                    lower_rad=float(j.find('limit').attrib['lower']),upper_rad=float(j.find('limit').attrib['upper']))
            result.append(row);done.add(row['child']);remaining.remove(j);progress=True
        if not progress:raise ValueError('Invalid robot chain')
    geometry=json.loads(Path(boxes).read_text())
    return dict(schema='labsim.public_robot_numeric_model.v1',units='m',angle_units='rad',base_frame=base,tcp_frame='right_gripper',
        source_URDF_logical_path='robots/franka/lula_franka_gen.urdf',source_URDF_SHA256=SOURCE_URDF_SHA256,
        source_robot_boxes_SHA256=SOURCE_BOXES_SHA256,robot_input_asset_SHA256=geometry['robot_asset_SHA256'],
        joint_order=[f'panda_joint{i}' for i in range(1,8)],selected_frames=list(FRAMES),joints=result,
        nominal_authored_local_boxes={name:{key:geometry['links'][name][key] for key in ('local_min_m','local_max_m')} for name in FRAMES},
        geometry_scope='Per-link conservative AABB of authored collision INPUT vertices only; not cooked shapes, fingers/held vessel, contact offset or scene clearance',
        regeneration='python -m policy.robot_self_kinematics --urdf SOURCE_URDF --boxes LOCKED_PUBLIC_BOXES --output NEW_MODEL_JSON')


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Offline locked numeric robot model generation; no simulator/network')
    p.add_argument('--urdf',type=Path,required=True);p.add_argument('--boxes',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();value=generate_numeric_model(a.urdf,a.boxes)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as stream:stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(_sha(a.output))
