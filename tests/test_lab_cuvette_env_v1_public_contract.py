"""Focused CPU boundary/metadata tests; no Isaac or physical result is simulated."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from omegaconf import OmegaConf
from tasks.lab_cuvette_loading_env_v1 import LabCuvetteLoadingEnvV1


class PublicEnvironmentContractTest(unittest.TestCase):
    def test_camera_metadata_whitelist_excludes_debug_and_unknown_future_fields(self):
        raw=dict(name='wrist_camera',physical_parent='/World/Franka/panda_hand',
            intrinsic_matrix_native=np.eye(3),world_pose_position_m=[1.,2.,3.],
            sensor_rendering_time_s=.1,renderer_debug={'distance_to_image_plane':{'center_m':.2}},
            pose_sources={'physics_hand_times_mount':{'available':True}},
            authored_parent_chain=[{'path':'private'}],configuration={'debug_render_diagnostics':True},
            future_private_field={'object_position_m':[9.,9.,9.]})
        env=object.__new__(LabCuvetteLoadingEnvV1)
        env.rig=SimpleNamespace(get_meta=lambda name:raw)
        public=env.get_camera_meta('wrist_camera')
        self.assertEqual(set(public),{'name','physical_parent','intrinsic_matrix_native','world_pose_position_m','sensor_rendering_time_s'})
        public['world_pose_position_m'][0]=99.;public['intrinsic_matrix_native'][0,0]=99.
        self.assertEqual(raw['world_pose_position_m'][0],1.);self.assertEqual(raw['intrinsic_matrix_native'][0,0],1.)
        with self.assertRaises(ValueError):env.get_camera_meta('wrist_camera',debug=True)

    def test_IK_metadata_counts_real_solver_calls_and_cache_hits(self):
        class Kinematics:
            calls=0
            def compute_inverse_kinematics(self,*args,**kwargs):self.calls+=1;return np.zeros(7),True
        kin=Kinematics()
        solver=SimpleNamespace(get_kinematics_solver=lambda:kin,get_end_effector_frame=lambda:'right_gripper',
            get_joints_subset=lambda:SimpleNamespace(make_articulation_action=lambda q,unused:SimpleNamespace(joint_indices=np.arange(7),joint_positions=q)))
        q=np.r_[np.zeros(7),.04,.04]
        env=object.__new__(LabCuvetteLoadingEnvV1)
        env.cfg=OmegaConf.create(dict(physics=dict(control_hz=60,hz=240),env=dict(max_action_duration_s=1.,
            gripper_effort_max_N=8.,action_max_joint_delta_rad=.5,action_max_translation_m=.1,action_max_rotation_rad=.2)))
        env.robot=SimpleNamespace(get_joint_positions=lambda:q.copy(),dof_properties={'lower':np.full(9,-3.),'upper':np.full(9,3.)})
        env.ctx={'old':OmegaConf.create(dict(robot=dict(max_velocity=[1.]*9,ik_position_tolerance_m=5e-5,ik_orientation_tolerance_rad=.003)))}
        env.solver=solver;env.episode_id='cpu_contract';env.control_steps=0;env.grip=.08;env.effort=8.;env.qcmd=q.copy()
        env._ik_seed=q[:7].copy();env._ik_goal=None;env._ik_solution=None
        env.debug=dict(actual_tcp_position_m=[0.,0.,0.],actual_tcp_quaternion_wxyz=[1.,0.,0.,0.])
        action=dict(type='ee_pose',episode_id=env.episode_id,observation_step=0,values=[0.,0.,0.,1.,0.,0.,0.])
        first=env._convert_action(action)[-1]['IK']
        second=env._convert_action(action)[-1]['IK']
        moved=copy.deepcopy(action);moved['values'][0]=.001
        third=env._convert_action(moved)[-1]['IK']
        self.assertEqual(kin.calls,2)
        self.assertEqual([x['unchanged_goal_cache_hit'] for x in (first,second,third)],[False,True,False])
        self.assertEqual([x['solver_called'] for x in (first,second,third)],[True,False,True])
        self.assertTrue(all(x['unchanged_goal_cache_enabled'] for x in (first,second,third)))
        self.assertNotIn('unchanged_goal_cached',first)

    def test_finalize_appends_unsampled_terminal_video_once_and_records_actual_times(self):
        class Writer:
            def __init__(self,*args):self.frames=[];self.released=False
            def write(self,frame):self.frames.append(frame.copy())
            def release(self):self.released=True
        with tempfile.TemporaryDirectory() as directory,patch('cv2.VideoWriter',Writer):
            env=object.__new__(LabCuvetteLoadingEnvV1)
            env.rig=SimpleNamespace(names=('side_camera','wrist_camera'),get_meta=lambda name:{'name':name})
            env.images={name:np.full((8,12,3),30,np.uint8) for name in env.rig.names}
            env.cfg=OmegaConf.create(dict(env=dict(task_type='grasp_hold',seed=1)))
            env.episode_dir=Path(directory);env.phase='TEST';env.t=0.;env._video_last_t=-1.;env._video_writers={};env._video_frame_times=[]
            self.assertTrue(env._write_video())
            env.t=1/60;self.assertFalse(env._write_video())
            env.ctx={};env._result=None;env.episode_id='cpu_contract';env.episode_wall=time.perf_counter();env.options={};env.control_steps=1;env.steps=4
            env.scorer=SimpleNamespace(finalize=lambda *args:dict(task_success=False,record_valid=True))
            env.collector=SimpleNamespace(finish_episode=lambda *args,**kwargs:dict(task_success=False,record_valid=True),_integrity_errors=[])
            writers=list(env._video_writers.values())
            env.finalize_episode('POLICY_BUDGET')
            self.assertTrue(all(len(writer.frames)==2 and writer.released for writer in writers))
            record=json.loads((Path(directory)/'video_timestamps.json').read_text())
            self.assertEqual(record['frame_simulation_times_s'],[0.,1/60])
            self.assertTrue(record['terminal_frame_appended_at_finalize'])
            env.finalize_episode('SHOULD_NOT_REPEAT')
            self.assertTrue(all(len(writer.frames)==2 for writer in writers))


if __name__=='__main__':unittest.main()
