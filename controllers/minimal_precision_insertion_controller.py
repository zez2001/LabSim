"""Fixed Cartesian expert, without search or correction from the tube/hole state."""
import numpy as np
from isaacsim.core.utils.types import ArticulationAction


class MinimalPrecisionInsertionController:
    def __init__(self, cfg, robot, task):
        self.cfg,self.robot,self.task = cfg,robot,task
        self.last_ik_residual = 0.
        self.last_target = np.array(cfg.task.initial_tcp)

    def target_at(self, t):
        target = np.array(self.cfg.task.initial_tcp, dtype=float)
        if t < 2.:
            phase = 'CLAMP'
        elif t < self.cfg.task.release_time_s:
            phase = 'DESCEND'
            target[2] -= min((t-2.)*self.cfg.task.speed_m_s,
                self.cfg.task.initial_bottom_gap_m+self.cfg.task.target_depth_m)
        else:
            phase = 'RELEASE'
            target[2] -= self.cfg.task.initial_bottom_gap_m+self.cfg.task.target_depth_m
            if t >= self.cfg.task.retreat_time_s:
                phase = 'RETREAT' if t < self.cfg.task.check_time_s else 'STABILITY'
                target[2] += min((t-self.cfg.task.retreat_time_s)/3.,1.)*.04
        grip = .04*np.clip((t-self.cfg.task.release_time_s)/2.,0.,1.)
        return target, grip, phase

    def step(self, state):
        target,grip,phase = self.target_at(state['simulation_time'])
        if hasattr(self.task,'diagnostic_target'):
            target=self.task.diagnostic_target.copy()
            grip,phase=0.,'FREE_MOTION_DIAGNOSTIC'
        ik,valid = self.task.solver.compute_inverse_kinematics(target, self.task.scene['orientation'],
            position_tolerance=self.cfg.task.ik_position_tolerance_m,
            orientation_tolerance=self.cfg.task.ik_orientation_tolerance_rad)
        if not valid:
            self.task.status,self.task.reason = 'CONTROL_OR_IK_FAILURE','lula_target_unreachable'
            return None
        q = state['joint_positions'].copy()
        q[np.asarray(ik.joint_indices,dtype=int)] = ik.joint_positions
        q[7:] = grip
        fk,_ = self.task.solver.get_kinematics_solver().compute_forward_kinematics('right_gripper', q[:7])
        self.last_ik_residual = float(np.linalg.norm(fk-target))
        if self.task.phase!=phase:
            self.task.events.append(dict(event='PHASE_CHANGE',time=state['simulation_time'],phase=phase,target_tcp_m=target.tolist()))
        self.last_target,self.task.phase = target,phase
        self.task.target_tcp = target.copy()
        self.task.ik_residual = self.last_ik_residual
        return ArticulationAction(joint_positions=q)
