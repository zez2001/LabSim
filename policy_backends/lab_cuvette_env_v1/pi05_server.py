"""Auditable thin wrapper of the deployed RPent pi0.5 server.

The actual RLinf checkpoint/model implementation is inherited unchanged.
Adds endpoint identity, exact input/output evidence and timing.  No policy,
expert controller, simulator, checkpoint download or environment installation
is implemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from rpent.robots.components.pi05_vla_server import Pi05VLAFacade

from .policy_adapters import append_event


def _file_sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


class AuditedPi05VLAFacade(Pi05VLAFacade):
    def __init__(self, *, model_path: str, output_dir: str | Path, seed: int = 0):
        self.output = Path(output_dir).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.request_index = 0
        self.seed = int(seed)
        torch.manual_seed(self.seed)
        checkpoint = Path(model_path).resolve()
        started = time.perf_counter()
        super().__init__(model_path=str(checkpoint), embodiment='libero')
        self.metadata = {
            'schema': 'labsim.Env_v1.pi05_endpoint.v1',
            'checkpoint_id': 'RLinf-Pi05-LIBERO-130-fullshot-SFT',
            'checkpoint_path': str(checkpoint),
            'weights_sha256': _file_sha256(checkpoint / 'model.safetensors'),
            'norm_stats_sha256': _file_sha256(checkpoint / 'physical-intelligence/libero/norm_stats.json'),
            'embodiment': 'libero', 'output_action_dim': 7,
            'output_semantics': 'libero_normalized_osc_pose_delta_and_gripper_sign',
            'output_unnormalized_by_server': True,
            'model_class': type(self._model).__module__ + '.' + type(self._model).__name__,
            'action_chunk': int(self._model.config.action_chunk),
            'action_horizon': int(self._model.config.action_horizon),
            'model_load_and_hash_wall_s': time.perf_counter() - started,
            'torch_seed': self.seed,
            'truth_observation_used': False,
            'checkpoint_is_labsim_finetuned': False,
        }
        self._rpc['vla.get_metadata'] = self.get_metadata
        self._readonly_methods.add('vla.get_metadata')
        (self.output / 'model_metadata.json').write_text(json.dumps(self.metadata, indent=2) + '\n')

    def get_metadata(self):
        return self.metadata

    def predict(self, obs, options=None):
        self.request_index += 1
        index = self.request_index
        # Save the actual wire inputs before invoking the inherited model.
        source = {key: np.asarray(value) for key, value in obs.items()
                  if key != 'task_descriptions' and value is not None}
        np.savez_compressed(self.output / f'input_{index:06d}.npz', **source)
        input_record = {key: {'shape': list(a.shape), 'dtype': str(a.dtype),
                             'sha256': hashlib.sha256(a.tobytes()).hexdigest()}
                        for key, a in source.items()}
        inference_seed = (options or {}).get('inference_seed')
        if inference_seed is not None:
            torch.manual_seed(int(inference_seed))
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        try:
            actions = super().predict(obs, options)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            np.save(self.output / f'output_{index:06d}.npy', actions, allow_pickle=False)
            append_event(self.output / 'inference.jsonl', {
                'request_index': index, 'inputs': input_record,
                'task_descriptions': obs.get('task_descriptions'),
                'options': options, 'inherited_model_forward_wall_s': elapsed,
                'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None,
                'raw_server_output_actions': actions,
                'raw_server_output_shape': list(np.asarray(actions).shape),
                'actual_model_call': True, 'error': None,
            })
            return actions
        except Exception as exc:
            append_event(self.output / 'inference.jsonl', {
                'request_index': index, 'inputs': input_record, 'task_descriptions': obs.get('task_descriptions'),
                'options': options, 'wall_s_until_error': time.perf_counter() - start,
                'actual_model_call': True, 'error_type': type(exc).__name__, 'error': str(exc),
            })
            raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8098)
    p.add_argument('--seed', type=int, default=0)
    args = p.parse_args(argv)
    service = AuditedPi05VLAFacade(model_path=args.model_path, output_dir=args.output, seed=args.seed)
    service.serve(transport='http', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
