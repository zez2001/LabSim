"""Expert, physical action replay, and existing workspace policy evaluation."""
from collections import deque
import numpy as np
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.rotations import euler_angles_to_quat
from controllers.base_controller import BaseController


class MinimalPickController(BaseController):
    def __init__(self, cfg, robot, task):
        # The expert uses the scene's existing Lula solver; no RMPFlow is needed.
        self.cfg, self.robot, self.task = cfg, robot, task
        self.mode = cfg.mode
        self.reset_needed = False
        self._episode_num = 0
        self._language_instruction = cfg.task.instruction
        self._last_success = False
        self._last_failure_reason = ""
        self.pending = deque()
        if self.mode == "infer" and cfg.infer.type == "replay":
            import h5py
            with h5py.File(cfg.infer.replay_data_path, "r") as f:
                group = f if "actions" in f else f[cfg.infer.episode]
                if not np.isclose(group.attrs["control_hz"], cfg.task.control_hz):
                    raise ValueError("Replay control frequency does not match the task")
                self.replay = group["actions"][:]
        elif self.mode == "infer" and cfg.infer.type == "local":
            import torch
            import hydra
            import dill
            from omegaconf import OmegaConf
            # Trusted repository workspace checkpoint (state_dicts, not Lightning state_dict).
            payload = torch.load(cfg.infer.policy_model_path, map_location="cpu", pickle_module=dill,
                                 weights_only=False)
            self.policy_cfg = payload["cfg"]
            OmegaConf.register_new_resolver("eval", eval, replace=True)
            self.policy = hydra.utils.instantiate(self.policy_cfg.policy)
            key = "ema_model" if cfg.infer.use_ema and "ema_model" in payload["state_dicts"] else "model"
            self.policy.load_state_dict(payload["state_dicts"][key])
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.policy.to(self.device).eval()
            self.history = deque(maxlen=self.policy_cfg.n_obs_steps)
        elif self.mode == "infer" and cfg.infer.type == "remote":
            from controllers.inference_engines.remote_inference_engine import RemoteInferenceEngine
            self.remote_engine = RemoteInferenceEngine(cfg, trajectory_controller=None)
            self.history = deque(maxlen=cfg.infer.n_obs_steps)
            self.device = "cpu"
        elif self.mode != "collect":
            raise ValueError("Supported modes: collect, infer/replay, infer/local, infer/remote")
        self.reset()

    def reset(self):
        self.index = 0
        self.pending.clear()
        self.reset_needed = False
        if hasattr(self, "history"):
            self.history.clear()
        if hasattr(self, "policy") and hasattr(self.policy, "reset"):
            self.policy.reset()

    def expert(self, state):
        grip = self.task.initial_position + np.array([0.0, 0.0, self.task.height * 0.55])
        approach, lift = grip + [0, 0, 0.16], grip + [0, 0, 0.12]
        phases = [(3., approach, approach, .04), (2., approach, grip, .04),
                  (1.5, grip, grip, 0.), (2.5, grip, lift, 0.), (3., lift, lift, 0.)]
        t = state["simulation_time"]
        for duration, start, end, aperture in phases:
            if t < duration:
                break
            t -= duration
        f = np.clip(t / duration, 0, 1)
        target = start + f * f * (3 - 2 * f) * (end - start)
        ik, reachable = self.task.solver.compute_inverse_kinematics(
            target, euler_angles_to_quat(np.array([np.pi, 0., 0.])))
        if not reachable:
            raise RuntimeError("Expert inverse kinematics target is unreachable")
        q = state["joint_positions"].copy()
        q[np.asarray(ik.joint_indices, dtype=int)] = ik.joint_positions
        return np.concatenate([q[:7], [aperture]])

    def predict(self, state):
        import torch
        self.history.append(state)
        while len(self.history) < self.history.maxlen:
            self.history.append(state)
        if not self.pending:
            obs = {key: torch.as_tensor(np.stack([s["camera_data"][key] for s in self.history]),
                                        device=self.device).float().unsqueeze(0) / 255.
                   for key in state["camera_data"]}
            obs["agent_pose"] = torch.as_tensor(np.stack([s["joint_positions"][:8] for s in self.history]),
                                                device=self.device).float().unsqueeze(0)
            if hasattr(self, "remote_engine"):
                for key in state["camera_data"]:
                    obs[key] = obs[key].permute(0, 1, 3, 4, 2)
                prediction = self.remote_engine._predict_action(obs, state["language_instruction"])
            elif "ACT" in self.policy_cfg.policy._target_:
                obs = {k: v[:, -1] for k, v in obs.items()}
                with torch.no_grad():
                    prediction = self.policy.predict_action(obs)["action"][0].cpu().numpy()
            else:
                with torch.no_grad():
                    prediction = self.policy.predict_action(obs)["action"][0].cpu().numpy()
            if prediction.ndim != 2 or prediction.shape[1] != 8 or len(prediction) == 0:
                raise ValueError("Inference must return a nonempty [T, 8] action chunk")
            self.pending.extend(prediction)
        return self.pending.popleft()

    def step(self, state):
        if state["done"]:
            self.reset_needed = True
            self._last_success = self.task.status == "SUCCESS"
            self._last_failure_reason = self.task.reason
            return None, True, self._last_success
        if self.mode == "collect":
            target = self.expert(state)
        elif self.cfg.infer.type == "replay":
            # Hold the final target if the recording ends before the evaluation criterion.
            target = self.replay[min(self.index, len(self.replay) - 1)]
        else:
            target = self.predict(state)
        self.index += 1
        if target.shape != (8,) or not np.isfinite(target).all():
            raise ValueError("Policy must output 8 finite absolute joint position targets")
        limits = np.array([[-2.8973, 2.8973], [-1.7628, 1.7628], [-2.8973, 2.8973],
                           [-3.0718, -.0698], [-2.8973, 2.8973], [-.0175, 3.7525],
                           [-2.8973, 2.8973], [0., .04]])
        target = np.clip(target, limits[:, 0], limits[:, 1])
        action = ArticulationAction(joint_positions=np.concatenate([target[:7], [target[7], target[7]]]))
        return action, False, False

    def close(self):
        if hasattr(self, "remote_engine"):
            self.remote_engine.close()

    def print_failure_reason(self):
        print(self.task.reason, flush=True)

    def episode_num(self):
        return self._episode_num

    def is_success(self):
        return self.task.status == "SUCCESS"
