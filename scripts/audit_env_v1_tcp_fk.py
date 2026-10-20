"""Read-only URDF FK audit of actual Env_v1 joints, TCP and teacher/IK targets.

This uses XML+NumPy/SciPy, without importing Isaac, Lula or starting simulation.
It is an independent reproduction of the installed Lula URDF transform chain,
not a physical calibration or an alternative source of task success labels.
"""
from __future__ import annotations
import argparse,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
import h5py,numpy as np,yaml
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_URDF=ROOT.parent/'labutopia-env/lib/python3.11/site-packages/isaacsim/exts/isaacsim.robot_motion.motion_generation/motion_policy_configs/franka/lula_franka_gen.urdf'


def transform(xyz=(0,0,0),rpy=(0,0,0)):
    result=np.eye(4);result[:3,:3]=Rotation.from_euler('xyz',rpy).as_matrix();result[:3,3]=xyz
    return result


def chain(urdf,target):
    joints={j.find('child').attrib['link']:j for j in ET.parse(urdf).getroot().findall('joint')}
    result=[]
    while target in joints:
        item=joints[target];origin=item.find('origin');axis=item.find('axis')
        xyz=[float(x) for x in origin.attrib.get('xyz','0 0 0').split()] if origin is not None else [0,0,0]
        rpy=[float(x) for x in origin.attrib.get('rpy','0 0 0').split()] if origin is not None else [0,0,0]
        direction=np.array([float(x) for x in axis.attrib.get('xyz','1 0 0').split()]) if axis is not None else np.array([1.,0,0])
        name=item.attrib['name'];index=int(name.removeprefix('panda_joint'))-1 if name.startswith('panda_joint') and item.attrib['type']!='fixed' else None
        result.append((name,item.attrib['type'],transform(xyz,rpy),direction,index));target=item.find('parent').attrib['link']
    return list(reversed(result))


def forward(parts,q,base):
    value=base.copy()
    for name,kind,origin,axis,index in parts:
        value=value@origin
        if kind in ('revolute','continuous'):
            motion=np.eye(4);motion[:3,:3]=Rotation.from_rotvec(axis*float(q[index])).as_matrix();value=value@motion
        elif kind=='prismatic':
            motion=np.eye(4);motion[:3,3]=axis*float(q[index]);value=value@motion
        elif kind!='fixed':raise ValueError('Unsupported URDF joint '+name+': '+kind)
    return value


def error(a,b):
    return [float(np.linalg.norm(a[:3,3]-b[:3,3])),float(np.rad2deg(Rotation.from_matrix(a[:3,:3]@b[:3,:3].T).magnitude()))]


def recorded_pose(position,quaternion):
    T=np.eye(4);q=np.asarray(quaternion);T[:3,:3]=Rotation.from_quat(np.r_[q[1:],q[0]]).as_matrix();T[:3,3]=position
    return T


def audit(episode,urdf):
    episode,urdf=Path(episode),Path(urdf);cfg=yaml.safe_load((episode/'config.yaml').read_text())
    base=transform(cfg['robot']['base_m']);parts=chain(urdf,'right_gripper')
    rows=[json.loads(x) for x in (episode/'physics_records.jsonl').open()]
    actual=[];command=[];actual_positions=[]
    for row in rows:
        fk=forward(parts,row['joints9'],base);actual_positions.append(fk[:3,3].tolist())
        actual.append(error(fk,recorded_pose(row['actual_tcp_position_m'],row['actual_tcp_quaternion_wxyz'])))
        if row.get('command_FK_TCP_pose'):
            pose=row['command_FK_TCP_pose'];command.append(error(fk,recorded_pose(pose['position_m'],pose['quaternion_wxyz'])))
    with h5py.File(episode/'dataset/episode_0000.h5') as h:
        raw=[json.loads(v) for v in h['actions_raw_json'].asstr()[:]];qcmd=h['control_auxiliary/command_q'][:]
        command_fk=[];target_errors=[];static=[]
        for i,(action,q) in enumerate(zip(raw,qcmd)):
            fk=forward(parts,q,base);command_fk.append(fk[:3,3].tolist())
            if action.get('type')=='ee_pose':
                target=recorded_pose(action['values'][:3],action['values'][3:]);target_errors.append(error(fk,target))
                if action.get('metadata',{}).get('teacher_phase')=='RESET':static.append(i)
        if static:
            same=np.asarray([raw[i]['values'] for i in static]);j=qcmd[static,:7]
            static_info=dict(samples=len(static),requested_pose_max_abs_change=float(np.max(np.abs(same-same[0]))),
                command_joint_max_abs_change_rad=float(np.max(np.abs(j-j[0]))),
                command_FK_position_max_change_m=float(np.max(np.linalg.norm(np.asarray(command_fk)[static]-np.asarray(command_fk)[static[0]],axis=1))))
        else:static_info=None
    values=np.asarray(actual);targets=np.asarray(target_errors)
    return dict(schema='labsim.Env_v1.actual_URDF_FK_audit.v1',episode=str(episode.resolve()),
        urdf=str(urdf.resolve()),urdf_sha256=hashlib.sha256(urdf.read_bytes()).hexdigest(),
        physical_samples=len(rows),method='URDF parent origin xyz/RzRyRx times revolute axis q; configured world base translation and identity orientation; right_gripper frame',
        simulated=False,physical_calibration=False,
        actual_joints_URDF_FK_vs_recorded_PhysX_TCP=dict(max_position_error_m=float(values[:,0].max()),
            max_orientation_error_deg=float(values[:,1].max()),first_error=actual[0],last_error=actual[-1],
            worst_sample=rows[int(values[:,0].argmax())]['physics_step']),
        executed_command_joints_URDF_FK_vs_requested_EE=dict(max_position_error_m=float(targets[:,0].max()) if len(targets) else None,
            max_orientation_error_deg=float(targets[:,1].max()) if len(targets) else None,last_error=target_errors[-1] if target_errors else None),
        fixed_RESET_requested_pose=static_info,
        first_actual_FK_position_m=actual_positions[0],last_actual_FK_position_m=actual_positions[-1],
        actual_FK_trajectory_displacement_m=float(np.linalg.norm(np.asarray(actual_positions[-1])-actual_positions[0])),
        evidence_scope='Recorded same-step joint FK vs physical TCP. This does not judge camera rendering association, geometry validity or task success.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('episode');parser.add_argument('--urdf',default=str(DEFAULT_URDF));parser.add_argument('--output',required=True)
    args=parser.parse_args();result=audit(args.episode,args.urdf);destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
