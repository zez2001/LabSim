"""Receipt and command-persistence contracts; no simulated physics claims."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment


class FakeTask:
    def __init__(self, path):
        self.episode_dir=path; self.episode_id='new'; self.control_steps=0; self.steps=4
        self.t=1/60; self.ended=False; self._result=None
        self.grip=.0101; self.effort=5.; self.qcmd=np.zeros(9)
        self.cfg=SimpleNamespace(physics=SimpleNamespace(control_hz=60))
        self.pose=dict(position_m=[0.,0.,1.],quaternion_wxyz=[1.,0.,0.,0.])
        self.commands=[]; self.reject=False; self.fault=None; self.lag=0.

    def get_observation(self):
        return dict(episode_id=self.episode_id,observation_id=f'new:{self.control_steps}',
            TCPpose=copy.deepcopy(self.pose),gripper_opening_m=.0107,
            joint_positions=np.zeros(9),images={})

    def plan_cartesian(self, references):
        self.references=references
        return dict(success=not self.reject,q7=[np.zeros(7) for _ in references],
            summary=dict(planned_ticks=0 if self.reject else len(references)),failure=dict(reason='LIMIT'))

    def step(self, action):
        self.commands.append(copy.deepcopy(action)); self.steps+=4; self.t+=1/60
        self.pose=dict(position_m=list(np.asarray(action['values'][:3])+[self.lag,0,0]),
                      quaternion_wxyz=action['values'][3:])
        if self.fault=='partial':
            self.steps-=2; self.t-=1/120
            raise RuntimeError('mid-control failure')
        self.control_steps+=1
        self.grip=action['gripper_opening_m']
        if self.fault=='after':raise RuntimeError('after physics and record')

    def hold_actual_joints(self):self.held=True

    def finalize_episode(self, reason, failure_type):
        self.ended=True; self._result=dict(termination_reason=reason,failure_type=failure_type)


def command(**kwargs):
    return dict(action_id='one',episode_id='new',observation_id='new:0',type='ee_delta',
        values=[.005,0,0,0,0,0],frame='world',duration_s=1.,**kwargs)


def test_target_and_interval_are_independent(tmp_path):
    task=FakeTask(tmp_path); task.lag=.002
    receipt=ProjectEnvironment(task).execute(command())
    assert receipt['accepted'] and receipt['execution_finished'] and receipt['completed']
    assert not receipt['target_reached'] and not receipt['safety_stopped']
    assert receipt['status']=='FINISHED'
    assert receipt['final_position_error_m']==pytest.approx(.002)
    assert receipt['executed_control_ticks']==60 and receipt['executed_physics_steps']==240
    assert receipt['executed_duration_s']==pytest.approx(1.)


def test_plan_rejection_is_not_partial_and_reserves_id(tmp_path):
    task=FakeTask(tmp_path); task.reject=True; env=ProjectEnvironment(task)
    receipt=env.execute(command())
    assert not receipt['accepted'] and not receipt['partial_execution']
    assert receipt['status']=='REJECTED'
    assert receipt['execution_finished'] and not receipt['target_reached']
    assert receipt['executed_control_ticks']==0 and receipt['executed_duration_s']==0
    assert receipt['observation_id_after']=='new:0' and not task.commands
    assert env.execute(command())==receipt


def test_hold_preserves_applied_latch_not_measured_opening(tmp_path):
    task=FakeTask(tmp_path); env=ProjectEnvironment(task)
    env.requested_opening=.009; env.requested_effort=5.
    env.execute(command(gripper_opening_m=.009,gripper_effort_limit_N=5.))
    assert all(c['gripper_opening_m']==.0101 for c in task.commands)
    assert all(c['gripper_effort_limit_N']==5. for c in task.commands)


@pytest.mark.parametrize('fault,completed,physics,elapsed', [('after',1,4,1/60),('partial',0,2,1/120)])
def test_exception_uses_actual_counters_and_never_replays(tmp_path,fault,completed,physics,elapsed):
    task=FakeTask(tmp_path); task.fault=fault; env=ProjectEnvironment(task)
    result=env.execute(command())
    assert result['executed_control_ticks']==completed
    assert result['executed_physics_steps']==physics
    assert result['executed_duration_s']==pytest.approx(elapsed)
    assert result['partial_execution'] and result['safety_stopped'] and task.held
    assert result['status']=='STOPPED'
    assert env.execute(command())==result and len(task.commands)==1


def test_tcp_frame_delta_and_rotation_have_one_fixed_start(tmp_path):
    task=FakeTask(tmp_path)
    task.pose['quaternion_wxyz']=np.roll(Rotation.from_euler('z',90,degrees=True).as_quat(),1).tolist()
    receipt=ProjectEnvironment(task).execute({**command(),'frame':'tcp'})
    assert receipt['target_reached']
    assert receipt['requested_target_TCP']['position_m']==pytest.approx([0.,.005,1.])
    assert task.commands[0]['values'][:3]==pytest.approx([0.,.005/60,1.])


def test_completed_receipt_is_idempotent_with_stale_observation(tmp_path):
    task=FakeTask(tmp_path);env=ProjectEnvironment(task)
    first=env.execute(command());assert env.execute(command())==first
    assert len(task.commands)==60
    with pytest.raises(ValueError,match='different payload'):
        env.execute({**command(),'values':[.004,0,0,0,0,0]})


def test_new_backend_failure_cannot_rewrite_an_ended_result(tmp_path):
    task=FakeTask(tmp_path);env=ProjectEnvironment(task)
    env.finish('stop',failure_type='EXECUTOR_FAILURE')
    env.finish('service',failure_type='MODEL_SERVICE_ERROR')
    assert task._result['termination_reason']=='stop'
