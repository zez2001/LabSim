"""Pinned public RLinf/OpenPI inference with the existing LIBERO action adapter.

Run in a separate existing policy+Isaac Python. No training, teacher fallback,
checkpoint mutation or package installation occurs in this module.
"""

import hashlib
import inspect
import os
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from policy_backends.lab_cuvette_env_v1.policy_adapters import (
    LiberoTransferContract,
    Pi05LiberoAdapter,
)
from policy_backends.lab_cuvette_env_v1.pi05_rollout import run_pi05_rollout


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


class OpenPiModel:
    """Use official inference transforms and original fixed checkpoint weights."""

    def __init__(self, checkpoint, output):
        import torch
        from safetensors.torch import load_model
        from openpi import transforms
        from openpi.models.pi0_config import Pi0Config
        from openpi.models.model import ModelType
        from openpi.models.tokenizer import PaligemmaTokenizer
        from openpi.models_pytorch.pi0_pytorch import PI0Pytorch
        from openpi.policies.libero_policy import LiberoInputs, LiberoOutputs
        from openpi.policies.policy import Policy
        from openpi.shared.normalize import load
        from policy_backends.lab_cuvette_env_v1.input_audit import AuditedInputTransform

        checkpoint, self.output = Path(checkpoint), Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        contract = LiberoTransferContract()
        weights = checkpoint / "model.safetensors"
        norm = checkpoint / "physical-intelligence/libero/norm_stats.json"
        if (
            digest(weights) != contract.expected_weights_sha256
            or digest(norm) != contract.expected_norm_stats_sha256
        ):
            raise ValueError("Checkpoint differs from pinned LabSim LIBERO weights/normalization")
        # These are RLinf/openpi's pi05_libero inference settings, with no extra
        # delta transform. Torch eager mode avoids recompilation during smoke tests.
        config = Pi0Config(pi05=True, action_horizon=10, discrete_state_input=False)
        torch.manual_seed(0)
        model = PI0Pytorch(config)
        load_model(model, str(weights), strict=True)
        model.paligemma_with_expert.to_bfloat16_for_selected_params("bfloat16")
        norm_stats = load(norm.parent)
        self.policy = Policy(
            model,
            transforms=[
                LiberoInputs(ModelType.PI05),
                transforms.Normalize(norm_stats, use_quantiles=True),
                transforms.ResizeImages(224, 224),
                transforms.TokenizePrompt(
                    PaligemmaTokenizer(config.max_token_len), discrete_state_input=False
                ),
                transforms.PadStatesAndActions(config.action_dim),
            ],
            output_transforms=[
                transforms.Unnormalize(norm_stats, use_quantiles=True),
                LiberoOutputs(),
            ],
            is_pytorch=True,
            pytorch_device="cuda",
            sample_kwargs={"num_steps": 10},
        )
        self.index = 0
        self.policy._input_transform = AuditedInputTransform(
            self.policy._input_transform,
            self.output / "effective_input_audit.jsonl",
            lambda: self.index,
        )
        self.metadata = dict(
            checkpoint_id=contract.checkpoint_id,
            weights_sha256=contract.expected_weights_sha256,
            norm_stats_sha256=contract.expected_norm_stats_sha256,
            implementation="RLinf/openpi",
            expected_implementation_commit="c5dc4b9296a1a4739bf52828f28a579f12dce763",
            implementation_files_sha256={
                Path(inspect.getfile(cls)).name: digest(inspect.getfile(cls))
                for cls in (PI0Pytorch, Pi0Config, Policy, PaligemmaTokenizer)
            },
            model_class=type(model).__name__,
            embodiment="libero",
            output_action_dim=7,
            output_semantics="libero_normalized_osc_pose_delta_and_gripper_sign",
            output_unnormalized_by_server=True,
            checkpoint_is_labsim_finetuned=False,
            action_horizon=10,
            discrete_state_input=False,
            quantile_normalization=True,
            torch_version=torch.__version__,
            torch_compile_disabled=os.environ.get("TORCHDYNAMO_DISABLE") == "1",
        )
        (self.output / "model_metadata.json").write_text(json.dumps(self.metadata, indent=2))

    def predict(self, obs, options=None):
        self.index += 1
        inputs = {
            "observation/state": obs["states"],
            "observation/image": obs["main_images"],
            "observation/wrist_image": obs["wrist_images"],
            "prompt": obs["task_descriptions"],
        }
        np.savez_compressed(self.output / f"input_{self.index:04d}.npz", **inputs)
        actions = self.policy.infer(inputs)["actions"]
        np.save(self.output / f"output_{self.index:04d}.npy", actions, allow_pickle=False)
        return actions


class UnitPi05Adapter(Pi05LiberoAdapter):
    """Swap the optional RPent transport for the same pinned local model."""

    def __init__(self, model, base_position, control_hz=120):
        self.contract = LiberoTransferContract(
            control_hz=control_hz,
            execution_translation_cap_m=0.0005,
            execution_rotation_cap_rad=0.004,
        )
        self.server_metadata = model.metadata
        self._model = model
        self.base_position = np.asarray(base_position)
        self.base_rotation = Rotation.identity()
        self.reset()


class LocalEnvironment:
    """The existing rollout consumes the current release RPC step contract."""

    def __init__(self, facade):
        from demos.cell_units.rpc import UnitRPC

        self.facade, self.rpc = facade, UnitRPC(facade)

    def get_observation(self):
        return self.facade.observe()

    def step(self, action):
        return self.rpc.step(action)


def run(facade, model, output, max_calls=120, max_actions=600):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(actual_model_requests=0, executed_actions=0, termination_reason="POLICY_BUDGET")
    initial = facade.observe()
    adapter = UnitPi05Adapter(
        model, facade.task.robot.get_world_pose()[0], facade.task.cfg.physics.control_hz
    )
    try:
        run_pi05_rollout(
            LocalEnvironment(facade),
            adapter,
            facade.observe(),
            result,
            output=output,
            maximum_model_requests=max_calls,
            maximum_actions=max_actions,
        )
    except Exception as error:
        facade.finish("PI05_POLICY_ERROR", failure_type="MODEL_SERVICE_ERROR")
        result.update(error_type=type(error).__name__, termination_reason="PI05_POLICY_ERROR")
        raise
    finally:
        result["status"] = facade.finish(result["termination_reason"])
        result["task_success"] = result["status"]["task_success"]
        xyz = np.asarray(
            [initial["TCPpose"]["position_m"]]
            + [row["end_effector_m"] for row in facade.task.records]
        )
        result["measured_tcp_path_m"] = float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum())
        result["measured_tcp_max_excursion_m"] = float(np.linalg.norm(xyz - xyz[0], axis=1).max())
        result["arm_motion_observed"] = result["measured_tcp_max_excursion_m"] > 0.0001
        result["arm_motion_threshold_m"] = 0.0001
        result["action_protocol_complete"] = result.get("integration_complete", False)
        result["integration_complete"] = (
            result["action_protocol_complete"] and result["arm_motion_observed"]
        )
        (output / "summary.json").write_text(json.dumps(result, indent=2))
    return result
