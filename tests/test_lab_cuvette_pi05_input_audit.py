"""CPU contracts for input observability without changing policy numerics."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from policy_backends.lab_cuvette_env_v1.input_audit import (
    AuditedInputTransform, array_spec, audit_saved_input, token_audit,
)
from policy_backends.lab_cuvette_env_v1.policy_adapters import Pi05LiberoAdapter


class FakeSentencePiece:
    def encode(self, text, add_bos=False):
        return ([2] if add_bos else []) + [ord(c) + 10 for c in text]

    def decode(self, tokens):
        return ''.join(chr(t - 10) for t in tokens if t >= 10)

    def bos_id(self): return 2
    def eos_id(self): return 1
    def pad_id(self): return 0
    def vocab_size(self): return 512
    def serialized_model_proto(self): return b'test-model-only'


class FakeTokenizer:
    def __init__(self, limit):
        self._max_len = limit
        self._tokenizer = FakeSentencePiece()


def transform(limit=200):
    return SimpleNamespace(tokenizer=FakeTokenizer(limit), discrete_state_input=False)


def test_text_audit_distinguishes_effective_prefix_and_discarded_suffix():
    tf = transform(8)
    raw = tf.tokenizer._tokenizer.encode('abc def xyz', add_bos=True) + tf.tokenizer._tokenizer.encode('\n')
    audit = token_audit(tf, ' abc_def\nxyz ', None, np.asarray(raw[:8]), np.ones(8, dtype=bool))
    assert audit['truncated'] and audit['raw_token_count'] == 13
    assert audit['active_token_count'] == 8
    assert audit['effective_decoded'] == 'abc def'
    assert audit['discarded_decoded'] == ' xyz\n'
    assert audit['output_matches_installed_formatting']
    assert audit['add_bos'] and not audit['add_eos']
    assert not audit['eos_present_in_effective']


def test_text_audit_does_not_silently_verify_changed_processor():
    tf = transform(5)
    report = token_audit(tf, 'ab', None, np.asarray([2, 107, 108, 99, 0]), np.asarray([1, 1, 1, 1, 0]))
    assert not report['output_matches_installed_formatting']


def test_live_wrapper_calls_processor_once_and_returns_exact_original_arrays(tmp_path):
    tf = transform(5)
    # Match the actual installed transform's discoverable identity.
    TokenizePrompt = type('TokenizePrompt', (SimpleNamespace,), {})
    tf = TokenizePrompt(tokenizer=tf.tokenizer, discrete_state_input=False)
    result = dict(state=np.zeros(32, dtype=np.float32),
                  tokenized_prompt=np.asarray([2, 107, 108, 20, 0]),
                  tokenized_prompt_mask=np.asarray([True, True, True, True, False]),
                  image={'base_0_rgb': np.arange(36, dtype=np.uint8).reshape(3, 4, 3)},
                  image_mask={'base_0_rgb': np.True_})
    class Processor:
        transforms = [tf]
        calls = 0
        def __call__(self, sample):
            self.calls += 1
            return result
    processor = Processor()
    before = result['image']['base_0_rgb'].copy()
    audited = AuditedInputTransform(processor, tmp_path / 'audit.jsonl', lambda: 7)
    observed = audited({'prompt': 'ab', 'observation/state': np.zeros(8)})
    assert observed is result and processor.calls == 1
    assert np.array_equal(observed['image']['base_0_rgb'], before)
    receipt = json.loads((tmp_path / 'audit.jsonl').read_text())
    assert receipt['request_index'] == 7
    assert receipt['image']['base_0_rgb'] == array_spec(before)
    assert receipt['output_matches_installed_formatting']


def test_adapter_keeps_native_rgb_bytes_and_resolution():
    adapter = Pi05LiberoAdapter.__new__(Pi05LiberoAdapter)
    adapter.base_position = np.zeros(3)
    adapter.base_rotation = Rotation.identity()
    side = np.arange(480 * 640 * 3, dtype=np.uint8).reshape(480, 640, 3)
    wrist = np.flip(side, axis=1).copy()
    observation = dict(task_language='Load the cuvette', images={'side_camera': side, 'wrist_camera': wrist},
                       joint_positions=np.zeros(9), TCPpose=dict(position_m=[0, 0, 1], quaternion_wxyz=[1, 0, 0, 0]))
    encoded = adapter.encode_observation(observation)
    assert encoded['main_images'] is side and encoded['wrist_images'] is wrist
    assert encoded['main_images'].shape == (480, 640, 3)
    assert encoded['main_images'].dtype == np.uint8
    assert encoded['states'].shape == (8,) and encoded['states'].dtype == np.float32


def test_preflight_rejects_saved_wire_receipt_mismatch_before_loading_processor(tmp_path, monkeypatch):
    wire = tmp_path / 'input.npz'
    np.savez(wire, main_images=np.zeros((1, 4, 5, 3), dtype=np.uint8),
             wrist_images=np.zeros((1, 4, 5, 3), dtype=np.uint8), states=np.zeros((1, 8), dtype=np.float32))
    log = tmp_path / 'inference.jsonl'
    log.write_text(json.dumps(dict(request_index=1, task_descriptions=['load'], inputs={'main_images': {}})) + '\n')
    def forbidden(*args):
        pytest.fail('The processor must not load for mismatched recorded evidence')
    monkeypatch.setattr('policy_backends.lab_cuvette_env_v1.input_audit.deployed_processor', forbidden)
    with pytest.raises(ValueError, match='Saved input differs'):
        audit_saved_input(tmp_path, wire, log, 1, tmp_path / 'new_audit')
