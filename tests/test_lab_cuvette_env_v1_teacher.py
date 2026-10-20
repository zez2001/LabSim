"""Teacher action-math checks, never claimed as real contact/robot execution."""
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
# Historical controllers/__init__ eagerly imports Isaac modules; load this
# standalone math/controller file without starting an unlicensed simulator.
import importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location('env_v1_teacher_math',Path(__file__).resolve().parents[1]/'controllers/lab_cuvette_env_v1_controller.py')
_module=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_module)
LabCuvetteTeacher,rotation,wxyz=_module.LabCuvetteTeacher,_module.rotation,_module.wxyz

class TeacherContractTest(unittest.TestCase):
    def setUp(self):
        self.cfg=dict(env=dict(task_type='grasp_hold'),physics=dict(control_hz=60,dynamic_friction=.5,finger_dynamic_friction=.8),
            vessel=dict(mass_kg=.02,yaw_deg=90),robot=dict(finger_kp=2000),gripper=dict(contact_safety_factor=2))
        self.layout=dict(source_floor=[-.085,-.175,.743],target_floor=[.21237,-.1499,.887],
            instrument_rotation=Rotation.from_euler('z',90,degrees=True).as_matrix(),target_rim_z=.914,source_rim_z=.768)
        self.controller=LabCuvetteTeacher(self.cfg,self.layout)
        self.hand=Rotation.from_euler('xyz',[180,0,-90],degrees=True)
        self.cup=Rotation.from_euler('z',90,degrees=True)
        self.debug=dict(actual_tcp_position_m=[-.085,-.175,.796],actual_tcp_quaternion_wxyz=wxyz(self.hand),
            object_position_m=[-.085,-.175,.743],object_quaternion_wxyz=wxyz(self.cup),finger_contact_N=[.1,.1],
            finger_joint_positions_m=[.0067,.0065],source_bottom_z_m=.743,tilt_deg=0,xy_error_target_m=[-.3,0])

    def test_latch_uses_actual_fingers_and_never_zero_after_contact(self):
        c=self.controller;c.act(dict(simulation_time=0,episode_id='fixture'),self.debug)
        c.phase='GRASP';c.phase_start=0;c.anchor=np.array(self.debug['actual_tcp_position_m'])
        c.act(dict(simulation_time=.1,episode_id='fixture'),self.debug)
        action=c.act(dict(simulation_time=.21,episode_id='fixture'),self.debug)
        expected=np.mean(self.debug['finger_joint_positions_m'])-.02*9.81/(2*np.sqrt(.5*.8))*2/2000
        self.assertAlmostEqual(action['gripper_opening_m'],2*expected)
        self.assertGreater(action['gripper_opening_m'],.01)
        self.assertEqual(action['gripper_effort_limit_N'],8.)
        self.assertEqual(c.events[-1]['event'],'contact_latched')
        self.assertTrue(action['metadata']['truth_pose_used'])

    def test_first_contact_freezes_before_persistence_and_lost_contact_resumes_slowly(self):
        c=self.controller;c.act(dict(simulation_time=0,episode_id='fixture'),self.debug)
        c.phase='GRASP';c.phase_start=0;c.anchor=np.array(self.debug['actual_tcp_position_m'])
        first=c.act(dict(simulation_time=.1,episode_id='fixture'),self.debug)
        self.assertAlmostEqual(first['gripper_opening_m'],sum(self.debug['finger_joint_positions_m']))
        self.assertIsNone(c.latch_opening)
        lost=dict(self.debug,finger_contact_N=[0.,0.])
        following=c.act(dict(simulation_time=.1+1/60,episode_id='fixture'),lost)
        self.assertAlmostEqual(first['gripper_opening_m']-following['gripper_opening_m'],.002/60)
        self.assertGreater(following['gripper_opening_m'],.01)

    def test_orientation_feedback_is_bounded_and_counters_passive_cup_tilt(self):
        c=self.controller;c.act(dict(simulation_time=0,episode_id='fixture'),self.debug)
        original=c.rotation_command
        tilted=dict(self.debug,object_quaternion_wxyz=wxyz(Rotation.from_euler('x',3,degrees=True)*self.cup))
        c._feedback(tilted)
        delta=(c.rotation_command*original.inv()).as_rotvec()
        self.assertAlmostEqual(np.linalg.norm(delta),np.deg2rad(.1),places=10)
        self.assertLess(delta[0],0)

    def test_unknown_bottom_support_never_triggers_release(self):
        self.assertFalse(self.controller._supported(dict(self.debug,target_bottom_support_N=None,target_bottom_gap_m=0)))

    def test_teacher_cannot_cross_episode_without_reset(self):
        self.controller.act(dict(simulation_time=0,episode_id='first'),self.debug)
        with self.assertRaises(ValueError):self.controller.act(dict(simulation_time=.1,episode_id='second'),self.debug)

if __name__=='__main__':unittest.main()
