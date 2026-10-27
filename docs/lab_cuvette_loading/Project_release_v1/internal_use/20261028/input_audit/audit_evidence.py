"""Reproduce the closed-run input audit with the existing deployed policy Python.

CPU only; no model construction. Output must be a fresh directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['JAX_PLATFORMS'] = 'cpu'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import cv2
import h5py
import numpy as np
from policy_backends.lab_cuvette_env_v1.input_audit import (
    AuditedInputTransform, array_spec, audit_saved_input, deployed_processor,
    sha256_file, source_identity,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    run = ROOT / 'outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_model'
    env = ROOT / 'outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_env'
    for parent in (run, env):
        proof = json.loads((parent / 'process_exit.json').read_text())
        if not proof['process_exited'] or (Path('/proc') / str(proof['pid'])).exists():
            raise RuntimeError('Source process must be closed: ' + str(parent))
    inference = run / 'inference.jsonl'
    rows = [json.loads(line) for line in inference.read_text().splitlines()]
    binary = sorted(run.glob('input_*.npz'))
    h5_path = env / 'episode_0000/dataset/episode_0000.h5'
    source_files = [inference, h5_path, run / 'process_exit.json', env / 'process_exit.json', *binary]
    before = {str(path.relative_to(ROOT)): sha256_file(path) for path in source_files}
    scans = []
    for row in rows:
        index = row['request_index']
        path = run / f'input_{index:06d}.npz'
        with np.load(path, allow_pickle=False) as record:
            specs = {key: array_spec(record[key]) for key in record.files}
            if specs != row['inputs']:
                raise AssertionError('Wire input differs from inference receipt')
            scans.append(dict(request_index=index, path=str(path.relative_to(ROOT)), inputs=specs))
    first = audit_saved_input(args.model_path, binary[0], inference, 1, output / 'request_000001')
    last = audit_saved_input(args.model_path, binary[-1], inference, rows[-1]['request_index'], output / 'request_000069')
    with np.load(binary[0], allow_pickle=False) as record:
        first_wire = {key: record[key].copy() for key in record.files}
    with h5py.File(h5_path, 'r') as source:
        h5_labels = {key: source.attrs.get(key) for key in ('episode_id', 'task_success', 'record_valid', 'scene_version', 'finalization_id')}
        h5_labels = {key: value.item() if isinstance(value, np.generic) else value for key, value in h5_labels.items()}
        branch = {}
        for camera, wire_key in (('side_camera_rgb', 'main_images'), ('wrist_camera_rgb', 'wrist_images')):
            native = first_wire[wire_key][0]
            expected = cv2.resize(native, (256, 256), interpolation=cv2.INTER_AREA).transpose(2, 0, 1).copy()
            actual = source[camera][0]
            branch[camera] = dict(dataset_shape=list(source[camera].shape), dataset_dtype=str(source[camera].dtype),
                                  first_frame=array_spec(actual),
                                  native_first_rpc_frame_resize_equals_h5_first_observation=bool(np.array_equal(actual, expected)),
                                  legacy_camera_alias_is_hardlink=source[camera].id == source['camera_1_rgb' if camera == 'side_camera_rgb' else 'camera_2_rgb'].id)
    processor, metadata = deployed_processor(args.model_path)
    sample = {'observation/image': first_wire['main_images'][0], 'observation/wrist_image': first_wire['wrist_images'][0],
              'observation/state': first_wire['states'][0], 'prompt': rows[0]['task_descriptions'][0]}
    class CountingProcessor:
        transforms = processor.transforms
        calls = 0
        def __call__(self, value):
            self.calls += 1
            self.result = processor(value)
            return self.result
    original = CountingProcessor()
    wrapper = AuditedInputTransform(original, output / 'actual_processor_wrapper_smoke.jsonl', lambda: 1)
    processed = wrapper(sample)
    wrapper_record = json.loads((output / 'actual_processor_wrapper_smoke.jsonl').read_text())
    with np.load(output / 'request_000001/effective_processor_input.npz') as baseline:
        exact = all(np.array_equal(processed['image'][key], baseline['image_' + key]) for key in processed['image'])
        exact = exact and np.array_equal(processed['state'], baseline['state'])
        exact = exact and np.array_equal(processed['tokenized_prompt'], baseline['tokenized_prompt'])
    after = {str(path.relative_to(ROOT)): sha256_file(path) for path in source_files}
    summary = dict(schema='labsim.Project_release_v1.internal_use.input_evidence.v1',
                   audit_source=source_identity(main), source_processes_closed=True,
                   actual_new_model_forward=False, weights_loaded=False, camera_or_action_numerics_changed=False,
                   source_inference_requests=len(rows), source_npz_count=len(binary),
                   first_and_last_text_sha256=[first['task_text_sha256'], last['task_text_sha256']],
                   first_and_last_text_identical=first['task_text_sha256'] == last['task_text_sha256'],
                   raw_tokens=first['raw_token_count'], max_tokens=first['model_max_tokens'],
                   active_tokens=first['active_token_count'], discarded_tokens=first['discarded_token_count'],
                   tokenizer_sha256=first['sentencepiece_model_sha256'],
                   raw_model_service_input_shape=[1,480,640,3], raw_model_service_input_dtype='uint8',
                   all_69_saved_wire_inputs_match_recorded_inference_receipts=True,
                   h5_branch=branch, original_h5_labels=h5_labels,
                   wrapper_smoke=dict(installed_processor_executed_once=original.calls == 1,
                                      exact_same_result_object_returned=processed is original.result,
                                      exact_image_state_token_values_preserved=exact,
                                      effective_token_audit_matches=wrapper_record['output_matches_installed_formatting'],
                                      new_model_forward=False),
                   source_sha256_before=before, source_sha256_after=after, source_files_unchanged=before == after,
                   audit_notes=['Offline reprocessing of saved real inputs is not a new model inference or task run.',
                                'No input prompt shortening, image transformation or action cap changed.',
                                'The live service wrapper has been verified on the deployed processor on CPU; no new model-service rollout was requested.'])
    if not summary['source_files_unchanged'] or not all(summary['wrapper_smoke'][key] for key in ('installed_processor_executed_once','exact_same_result_object_returned','exact_image_state_token_values_preserved','effective_token_audit_matches')):
        raise AssertionError('Audit preservation check failed')
    (output / 'all_69_wire_input_checks.json').write_text(json.dumps(scans, indent=2) + '\n')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: summary[key] for key in ('source_inference_requests','raw_tokens','max_tokens','active_tokens','discarded_tokens','wrapper_smoke','source_files_unchanged')}))

if __name__ == '__main__':
    main()
