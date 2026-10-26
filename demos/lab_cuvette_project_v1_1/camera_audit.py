"""Teacher camera QA sidecars, using the real provider encoder without control.

Capturing a preview makes no network request and advances no physics. Phase
names belong only to the reviewer sidecar, never to the public model input.
The optional comparison submits the already saved JPEG bytes, with no tools,
no motion, no retry, and the caller's existing shared provider budget.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time

from policy.backends.cubence import ProviderError, response_text
from policy.backends.cubence_tools import (
    PUBLIC_FIELDS, json_safe, observation_content, public_observation,
    save_observation_artifacts,
)


PROFILES = {
    '512low': dict(max_side_px=512, jpeg_quality=60, detail='low', resize_interpolation='lanczos'),
    '640high': dict(max_side_px=640, jpeg_quality=60, detail='high', resize_interpolation='lanczos'),
}
CAMERAS = ('side_camera', 'wrist_camera')
COMPARISON_PROMPT = (
    'This is a stationary camera quality check, not robot control. '
    'Describe what can actually be seen in the two synchronized RGB images: '
    'the gripper, light cuvette, source rack, instrument opening and internal seat. '
    'State occlusion or insufficient detail explicitly. Do not invent object '
    'coordinates, infer an unobserved task outcome, or issue robot actions.'
)


def _write(path, value):
    Path(path).write_text(json.dumps(json_safe(value), indent=2, ensure_ascii=False,
                                   allow_nan=False) + '\n', encoding='utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


class TeacherCameraAudit:
    """One instance per episode; the launcher owns reset, stepping and close."""

    def __init__(self, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.previous_phase = None
        self.snapshots = []
        _write(self.output / 'audit.json', dict(
            schema='labsim.Project_v1_1.teacher_camera_qa.v1',
            evidence_kind='teacher_encoded_preview', api_sent=False,
            profiles=PROFILES, source='One public facade.observe at each requested boundary',
            phase_scope='reviewer sidecar only; excluded from all model input',
            no_GT_crop=True, no_simulation_step=True, snapshots=[]))

    def capture_if_phase_changed(self, facade, phase):
        if phase == self.previous_phase:
            return None
        return self.capture(facade, phase, event='phase_boundary')

    def capture(self, facade, phase, *, event='phase_boundary'):
        from PIL import Image
        import numpy as np

        if not isinstance(phase, str) or not phase or len(phase) > 128:
            raise ValueError('A short reviewer phase name is required')
        observation = public_observation(facade.observe())
        index = len(self.snapshots)
        folder = self.output / f'stage_{index:06d}'
        folder.mkdir(exist_ok=False)
        native = folder / 'native_rgb'
        native.mkdir()
        record = dict(schema='labsim.Project_v1_1.teacher_camera_snapshot.v1',
            evidence_kind='teacher_encoded_preview', api_sent=False,
            snapshot_index=index, reviewer_phase=phase, reviewer_event=str(event),
            episode_id=observation['episode_id'], observation_id=observation['observation_id'],
            simulation_time_s=observation.get('simulation_time', observation.get('simulation_time_s')),
            native_rgb=[], profiles={}, no_GT_crop=True,
            source_frame_reencoded_for_preview=True, phase_in_public_input=False)
        for name in CAMERAS:
            value = np.asarray(observation.get('images', {}).get(name))
            if value.dtype != np.uint8 or value.ndim != 3 or value.shape[2] != 3:
                raise ValueError('Expected native HWC RGB uint8 for both public cameras')
            path = native / (name + '.png')
            Image.fromarray(value).save(path, format='PNG')
            encoded = path.read_bytes()
            record['native_rgb'].append(dict(camera_name=name,
                path=str(path.relative_to(folder)), sha256=_sha(encoded),
                rgb_sha256=_sha(value.tobytes()), resolution_wh=[value.shape[1], value.shape[0]],
                format='PNG', lossless=True, bytes=len(encoded)))
        # Both profiles originate from the same unmodified native RGB observation.
        for name, image_config in PROFILES.items():
            contents = observation_content(observation, image_config=image_config)
            files = save_observation_artifacts(contents, folder / name, index,
                f"teacher_preview:{observation['episode_id']}:{observation['observation_id']}:{index}:{name}")
            record['profiles'][name] = dict(image_config=image_config,
                artifacts=files, evidence_kind='teacher_encoded_preview', api_sent=False)
        _write(folder / 'stage.json', record)
        self.previous_phase = phase
        self.snapshots.append(dict(snapshot_index=index, reviewer_phase=phase,
            reviewer_event=str(event), path=str(folder.relative_to(self.output)),
            observation_id=record['observation_id'], simulation_time_s=record['simulation_time_s']))
        _write(self.output / 'audit.json', dict(
            schema='labsim.Project_v1_1.teacher_camera_qa.v1',
            evidence_kind='teacher_encoded_preview', api_sent=False, profiles=PROFILES,
            phase_scope='reviewer sidecar only; excluded from all model input',
            no_GT_crop=True, no_simulation_step=True, snapshots=self.snapshots))
        return record


def _checked_file(root, relative, expected_sha):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Preview path escapes its artifact directory')
    raw = path.read_bytes()
    if _sha(raw) != expected_sha:
        raise ValueError('Preview SHA256 mismatch')
    return raw


def load_preview_contents(snapshot, profile):
    """Rebuild input from saved bytes; never decode/re-encode either JPEG."""
    if profile not in PROFILES:
        raise ValueError('Only the two declared camera QA profiles are supported')
    snapshot = Path(snapshot)
    sidecar = json.loads((snapshot / 'stage.json').read_text())
    files = sidecar['profiles'][profile]['artifacts']
    root = snapshot / profile
    manifest_raw = _checked_file(root, files['manifest_path'], files['manifest_sha256'])
    manifest = json.loads(manifest_raw)
    if manifest['images'] != files['images'] or manifest['public_observation'] != files['public_observation']:
        raise ValueError('Preview manifest differs from snapshot sidecar')
    public = files['public_observation']
    text = _checked_file(root, public['path'], public['sha256']).decode('utf-8')
    state = json.loads(text)
    if set(state) - ((PUBLIC_FIELDS - {'images'}) | {'model_image_transforms'}):
        raise ValueError('Unexpected public input field')
    if state.get('episode_id') != sidecar['episode_id'] or state.get('observation_id') != sidecar['observation_id']:
        raise ValueError('Preview identity differs from snapshot')
    if [image['camera_name'] for image in files['images']] != list(CAMERAS):
        raise ValueError('Both cameras must remain in their declared order')
    contents = [dict(type='input_text', text=text)]
    for image in files['images']:
        name = image['camera_name']
        jpeg = _checked_file(root, image['path'], image['sha256'])
        transform = state['model_image_transforms'][name]
        if transform['transmitted_jpeg_sha256'] != image['sha256'] or transform['detail'] != PROFILES[profile]['detail']:
            raise ValueError('Preview image differs from declared encoding')
        contents.extend([dict(type='input_text', text='Synchronized RGB: ' + name),
            dict(type='input_image', image_url='data:image/jpeg;base64,' + base64.b64encode(jpeg).decode(),
                 detail=transform['detail'])])
    return contents


def compare_preview_requests(client, snapshot, output, *, max_output_tokens=256):
    """At most two actual requests, sequential, no tools/retry/robot environment.

    The client must use the existing shared ledger. This function never opens a
    simulation or discovers a credential; it receives the already bounded client.
    """
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 256:
        raise ValueError('Camera comparison output must be bounded to1..256 tokens')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    snapshot = Path(snapshot).resolve()
    sidecar = json.loads((snapshot / 'stage.json').read_text())
    evidence = dict(schema='labsim.Project_v1_1.camera_comparison.v1',
        evidence_kind='actual_API_camera_comparison', requested_model=client.cfg['model'],
        source_snapshot=str(snapshot), source_stage_sha256=_sha((snapshot / 'stage.json').read_bytes()),
        episode_id=sidecar['episode_id'], observation_id=sidecar['observation_id'],
        no_GT_crop=True, robot_actions_executed=0, prompt=COMPARISON_PROMPT,
        max_requests=2, retries_per_request=0, probes={}, budget_before=client.ledger.summary())
    # Validate both inputs before spending any budget on the first request.
    inputs = {profile: load_preview_contents(snapshot, profile) for profile in PROFILES}
    for profile, contents in inputs.items():
        label = f"camera_qa:{sidecar['episode_id']}:{sidecar['observation_id']}:{sidecar['snapshot_index']}:{profile}"
        # Duplicate only small exact encoded inputs into the comparison evidence.
        saved = save_observation_artifacts(contents, output / profile, 0, label)
        before = client.ledger.summary()
        probe = dict(request_label=label, image_config=PROFILES[profile], observation_artifacts=saved,
                     api_sent=False, network_attempts=0, max_output_tokens=max_output_tokens)
        payload = dict(model=client.cfg['model'], input=[dict(role='user', content=contents)],
                       instructions=COMPARISON_PROMPT, max_output_tokens=max_output_tokens, store=False)
        if client.cfg.get('reasoning_effort'):
            payload['reasoning'] = dict(effort=client.cfg['reasoning_effort'])
        started = time.monotonic()
        try:
            response, meta = client.request(payload, label=label, endpoint='responses', allow_retry=False,
                deadline_monotonic=started + min(float(client.cfg['episode_timeout_s']), 60.0))
            probe.update(status='COMPLETED', returned_model=response.get('model'),
                response_id=response.get('id'), usage=response.get('usage'),
                output_text=response_text(response)[:2000], request_id=meta.get('request_id'))
        except ProviderError as error:
            probe.update(status=error.code, http_status=error.status,
                timeout_observed='TIMEOUT' in error.code)
        after = client.ledger.summary()
        count = int(after.get('total_network_attempts', 0)) - int(before.get('total_network_attempts', 0))
        probe.update(network_attempts=count, api_sent=count > 0, wall_seconds=time.monotonic() - started)
        evidence['probes'][profile] = probe
        evidence['budget_after'] = after
        _write(output / 'comparison.json', evidence)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True, help='Closed stage_XXXXXX preview folder')
    parser.add_argument('--provider-config', type=Path, required=True)
    parser.add_argument('--budget-ledger', type=Path, required=True, help='Existing shared ledger; never create a new allowance')
    parser.add_argument('--output', type=Path, required=True, help='New output folder; existing evidence is not overwritten')
    parser.add_argument('--allow-network', action='store_true', help='Explicitly enable the two bounded real API comparisons')
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error('No API call made: comparison requires explicit --allow-network')
    if not args.budget_ledger.is_file():
        parser.error('Existing shared budget ledger is required')
    from policy.backends.cubence import BudgetLedger, CubenceClient, load_config
    cfg = load_config(args.provider_config)
    result = compare_preview_requests(CubenceClient(cfg, BudgetLedger(args.budget_ledger, cfg)),
                                      args.snapshot, args.output)
    print(json.dumps(dict(output=str(args.output),
        probes={k: v['status'] for k, v in result['probes'].items()}, budget=result['budget_after'])))
    return 0 if all(v['status'] == 'COMPLETED' for v in result['probes'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
