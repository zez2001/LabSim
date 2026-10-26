"""Opt-in public wrist-image memory for Project_v1_1, not a robot controller.

The existing Cubence client owns HTTP, credentials, retries and the shared
budget. This decorator only augments its *input before* token reservation. It
never reads an environment, object truth, teacher state, or physical result.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path

from .cubence import ProviderError, canonical_hash
from .cubence_tools import PUBLIC_FIELDS, compact_camera_metadata

VERSION = 'Project_v1_1.public_temporal_visual_context.v1'
VISUAL_CONTEXT = dict(enabled=True, previous_distinct_wrist=True,
    first_public_bilateral_wrist=True, bilateral_contact_threshold_N=.02)


def validate_visual_context(config):
    """Missing means the unchanged historical interface; explicit means exact v1."""
    if 'visual_context' not in config:
        return None
    value = config['visual_context']
    if (not isinstance(value, dict) or set(value) != set(VISUAL_CONTEXT)
            or any(value.get(k) is not True for k in ('enabled', 'previous_distinct_wrist', 'first_public_bilateral_wrist'))
            or isinstance(value.get('bilateral_contact_threshold_N'), bool)
            or not isinstance(value.get('bilateral_contact_threshold_N'), (int, float))
            or not math.isfinite(value['bilateral_contact_threshold_N'])
            or value['bilateral_contact_threshold_N'] != .02):
        raise ProviderError('PROTOCOL_INVALID_VISUAL_CONTEXT_CONFIG')
    return copy.deepcopy(value)


def _bytes_sha(value):
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def _public_snapshot(contents, decision_index, request_label):
    try:
        if not isinstance(contents, list) or len(contents) != 5 or contents[0].get('type') != 'input_text':
            raise ValueError('Expected exact current public state and two RGB blocks')
        state = json.loads(contents[0]['text'])
        allowed = (PUBLIC_FIELDS-{'images'}) | {'model_image_transforms'}
        if not isinstance(state, dict) or set(state)-allowed:
            raise ValueError('Unexpected current-state fields')
        for key in ('episode_id', 'observation_id'):
            if not isinstance(state.get(key), str) or not state[key]:
                raise ValueError('Missing public identity')
        stamp = state.get('simulation_time', state.get('simulation_time_s'))
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            raise ValueError('Invalid public time')
        # Detect JSON NaN anywhere without silently dropping or relabelling it.
        canonical_hash(state)
        images = {}
        for i, name in enumerate(('side_camera', 'wrist_camera')):
            label, image = contents[1+2*i:3+2*i]
            if label != dict(type='input_text', text='Synchronized RGB: '+name) or image.get('type') != 'input_image':
                raise ValueError('Unexpected image order')
            url = image.get('image_url', '')
            prefix = 'data:image/jpeg;base64,'
            if not isinstance(url, str) or not url.startswith(prefix):
                raise ValueError('Only exact encoded public JPEGs are accepted')
            encoded = base64.b64decode(url[len(prefix):], validate=True)
            if (not encoded.startswith(b'\xff\xd8') or
                    _bytes_sha(encoded) != state['model_image_transforms'][name]['transmitted_jpeg_sha256']):
                raise ValueError('JPEG provenance mismatch')
            images[name] = dict(block=copy.deepcopy(image), jpeg=encoded, sha256=_bytes_sha(encoded))
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        raise ProviderError('PROTOCOL_INVALID_TEMPORAL_PUBLIC_OBSERVATION') from None
    # History carries only whitelisted public robot/tactile/time and wrist
    # calibration. No task-private selector or result enters this projection.
    historical_keys = ('episode_id', 'observation_id', 'step_index', 'simulation_time',
        'simulation_time_s', 'joint_positions', 'joint_velocities', 'TCPpose', 'tcp_pose',
        'gripper_opening_m', 'gripper_effort_limit_N', 'finger_contact_N')
    historical = {k: copy.deepcopy(state[k]) for k in historical_keys if k in state}
    for name in ('TCPpose', 'tcp_pose'):
        if name in historical:
            historical[name] = {k: historical[name][k] for k in ('position_m', 'quaternion_wxyz') if k in historical[name]}
    for name in ('camera_meta', 'camera_calibration'):
        if name in state:
            historical[name] = dict(wrist_camera=compact_camera_metadata(state[name].get('wrist_camera', {})))
    transform = state['model_image_transforms']['wrist_camera']
    transform_keys = ('native_resolution_wh', 'transmitted_resolution_wh', 'scale_xy', 'native_rgb_sha256',
        'transmitted_jpeg_sha256', 'transmitted_bytes', 'jpeg_quality', 'detail', 'resize_interpolation',
        'crop', 'rotation_deg', 'color_space', 'transmitted_pixel_from_native_pixel',
        'intrinsic_matrix_transmitted', 'pixel_convention', 'native_recording_changed')
    historical['model_image_transforms'] = dict(wrist_camera={k: copy.deepcopy(transform[k]) for k in transform_keys if k in transform})
    return dict(state=state, historical=historical, images=images,
        episode_id=state['episode_id'], observation_id=state['observation_id'], time_s=float(stamp),
        source_decision_index=decision_index, source_request_label=request_label,
        source_contents=copy.deepcopy(contents))


def _bilateral(snapshot):
    forces = snapshot['state'].get('finger_contact_N')
    return (isinstance(forces, (list, tuple)) and len(forces) == 2
        and all(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v > .02 for v in forces))


def reconstruct_input_items(manifest_path):
    """Rebuild exact public/full inputs when no hidden reasoning was redacted.

    Reasoning response items remain in the live protocol but are never stored.
    Their presence makes exact full-input reconstruction deliberately unavailable.
    """
    path = Path(manifest_path)
    record = json.loads(path.read_text())
    if not record['exact_full_input_reconstructable']:
        raise ValueError('Hidden/opaque provider items were deliberately not persisted')
    def walk(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'image_url' and isinstance(item, dict) and item.get('encoding') == 'data:image/jpeg;base64':
                    source = (path.parent / item['path']).resolve()
                    image = source.read_bytes()
                    if _bytes_sha(image) != item['sha256']:
                        raise ValueError('Saved exact JPEG hash mismatch')
                    result[key] = 'data:image/jpeg;base64,'+base64.b64encode(image).decode('ascii')
                else:
                    result[key] = walk(item)
            return result
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value
    result = walk(record['input_items_public_projection'])
    if canonical_hash(result) != record['full_wire_input_canonical_sha256']:
        raise ValueError('Reconstructed input_items hash mismatch')
    return result


class PublicTemporalVisualClient:
    """Per-episode client decorator; performs no actions or additional API calls."""
    def __init__(self, client, output):
        validate_visual_context(client.cfg)
        self._client = client
        self.cfg = copy.deepcopy(client.cfg)
        self.ledger = client.ledger
        self.output = Path(output)
        self._episode = None
        self._last_distinct = None
        self._previous_distinct = None
        self._contact_reference = None
        self._decision_index = 0
        self._preflight_error_index = 0

    def reset(self):
        self._episode = None
        self._last_distinct = self._previous_distinct = self._contact_reference = None
        # Sequence numbers are output-local and cannot overwrite earlier proof.

    @staticmethod
    def _source_description(snapshot):
        return dict(episode_id=snapshot['episode_id'], observation_id=snapshot['observation_id'],
            simulation_time_s=snapshot['time_s'], source_decision_index=snapshot['source_decision_index'],
            source_request_label=snapshot['source_request_label'],
            wrist_jpeg_sha256=snapshot['images']['wrist_camera']['sha256'])

    def responses(self, input_items, *, instructions, tools=None, label='policy', deadline_monotonic=None, **extra):
        try:
            if (not isinstance(input_items, list) or not input_items or
                    not isinstance(input_items[-1], dict) or input_items[-1].get('role') != 'user'):
                raise ProviderError('PROTOCOL_TEMPORAL_CURRENT_OBSERVATION_MISSING')
            current = _public_snapshot(input_items[-1].get('content'), self._decision_index, label)
            if self._episode != current['episode_id']:
                self.reset()
                self._episode = current['episode_id']
            last = self._last_distinct
            duplicate = last is not None and last['observation_id'] == current['observation_id']
            if last is not None and ((duplicate and current['time_s'] != last['time_s'])
                    or (not duplicate and current['time_s'] <= last['time_s'])):
                raise ProviderError('PROTOCOL_TEMPORAL_OBSERVATION_TIME_INCONSISTENT')
            previous = self._previous_distinct if duplicate else last
            reference = self._contact_reference
            # A repeated observe does not establish new motion or replace the
            # first reference. A first public sample is only a contact candidate.
            selected_contact = reference is None and not duplicate and _bilateral(current)
            next_reference = current if selected_contact else reference
            candidates = []
            for role, snapshot in (('previous_distinct_wrist', previous), ('first_public_bilateral_wrist', reference)):
                if snapshot is None or snapshot['observation_id'] == current['observation_id']:
                    continue
                existing = next((v for v in candidates if v['snapshot']['observation_id'] == snapshot['observation_id']
                    and v['snapshot']['images']['wrist_camera']['sha256'] == snapshot['images']['wrist_camera']['sha256']), None)
                if existing is not None:
                    existing['roles'].append(role)
                else:
                    candidates.append(dict(roles=[role], snapshot=snapshot))
            historical = []
            if candidates:
                historical.append(dict(type='input_text', text=(
                    'HISTORICAL PUBLIC WRIST REFERENCES, NOT CURRENT OBSERVATIONS. '
                    'Use only the episode_id and observation_id in the final CURRENT user item for actions. '
                    'The first public bilateral-contact reference is not verified grasp, support, insertion or 3D object state. '
                    'Same pixels across these hand-mounted images do not establish equal world positions.')))
                for item in candidates:
                    snapshot = item['snapshot']
                    desc = dict(reference_roles=item['roles'], **self._source_description(snapshot),
                        public_robot_tactile_time_and_wrist_calibration=snapshot['historical'])
                    historical.append(dict(type='input_text', text=json.dumps(desc, ensure_ascii=False, allow_nan=False)))
                    historical.append(copy.deepcopy(snapshot['images']['wrist_camera']['block']))
            augmented = copy.deepcopy(input_items)
            if historical:
                augmented.insert(len(augmented)-1, dict(role='user', content=historical))
            # Persist the public projection before delegation, including any
            # later provider failure. Never alter/re-encode original artifacts.
            packet = self._save_packet(augmented, current, previous, next_reference, candidates,
                duplicate, selected_contact, label, bool(historical))
            if not duplicate:
                self._previous_distinct, self._last_distinct = last, current
            self._contact_reference = next_reference
            self._decision_index += 1
        except ProviderError as error:
            self._record_preflight_error(error.code)
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self._record_preflight_error('PROTOCOL_TEMPORAL_CONTEXT_RECORDING_FAILED')
            raise ProviderError('PROTOCOL_TEMPORAL_CONTEXT_RECORDING_FAILED') from None
        try:
            response = self._client.responses(augmented, instructions=instructions, tools=tools,
                label=label, deadline_monotonic=deadline_monotonic, **extra)
        except BaseException as error:
            outcome = dict(status='failed', error_type=type(error).__name__,
                error_code=error.code if isinstance(error, ProviderError) else None,
                credential_or_error_body_saved=False)
            (packet/'call_outcome.json').write_bytes(_json_bytes(outcome))
            raise
        (packet/'call_outcome.json').write_bytes(_json_bytes(dict(status='returned',
            credential_or_error_body_saved=False)))
        return response

    def _record_preflight_error(self, code):
        # Empty/malformed input must not serialize unvalidated data or touch the
        # provider. Preserve a safe failure record without overwriting packets.
        folder = self.output/'temporal_visual_context'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder/f'preflight_failure_{self._preflight_error_index:06d}.json'
            with path.open('xb') as stream:
                stream.write(_json_bytes(dict(schema=VERSION, decision_index=self._decision_index,
                    status='failed_before_delegate', error_code=code,
                    provider_called=False, unvalidated_input_or_credentials_saved=False)))
            self._preflight_error_index += 1
        except OSError:
            # The original failure still fails closed if the filesystem itself
            # cannot accept another proof; never overwrite existing evidence.
            pass

    def _save_packet(self, augmented, current, previous, reference, candidates,
                     duplicate, selected_contact, request_label, expanded):
        packet = self.output/'temporal_visual_context'/f'decision_{self._decision_index:06d}'
        packet.mkdir(parents=True, exist_ok=False)
        # Current artifacts were saved by the unchanged shared runner before
        # responses(). Refer to those exact files instead of encoding/copying.
        current_dir = self.output/'observations'/f'decision_{self._decision_index:06d}'
        image_paths = {}
        public_path = current_dir/'public_observation.json'
        if public_path.read_bytes() != current['source_contents'][0]['text'].encode('utf-8'):
            raise ValueError('Current saved public text differs from actual input')
        for name, image in current['images'].items():
            source = current_dir/(name+'.jpg')
            if source.read_bytes() != image['jpeg']:
                raise ValueError('Current saved JPEG differs from actual input')
            image_paths[image['sha256']] = source
        historical_records = []
        for index, item in enumerate(candidates):
            snapshot = item['snapshot'];image = snapshot['images']['wrist_camera']
            name=f'historical_{index:02d}_wrist.jpg';source=packet/name
            source.write_bytes(image['jpeg'])
            state_path=packet/f'historical_{index:02d}_public_observation.json'
            state_path.write_bytes(snapshot['source_contents'][0]['text'].encode('utf-8'))
            image_paths.setdefault(image['sha256'], source)
            historical_records.append(dict(reference_roles=item['roles'], **self._source_description(snapshot),
                exact_jpeg=dict(path=name, sha256=image['sha256'], bytes=len(image['jpeg'])),
                public_observation=dict(path=state_path.name,sha256=_bytes_sha(state_path.read_bytes()),
                    semantics='Exact original encoded public JSON; historical model message uses the declared robot/tactile/time/wrist-only projection')))
        redactions = []
        def project(value, item_index=None):
            if isinstance(value, dict):
                public_item_types = {'message', 'input_text', 'output_text', 'input_image', 'function_call', 'function_call_output'}
                if (('type' in value and value['type'] not in public_item_types)
                        or 'encrypted_content' in value):
                    redactions.append(dict(input_item_index=item_index, provider_item_type=value.get('type'),
                        canonical_sha256=canonical_hash(value)))
                    return dict(type='private_provider_item_not_persisted',
                        original_type=value.get('type'), canonical_sha256=canonical_hash(value))
                result = {}
                for key, item in value.items():
                    if key == 'image_url' and value.get('type') == 'input_image':
                        prefix='data:image/jpeg;base64,'
                        if not isinstance(item,str) or not item.startswith(prefix):
                            raise ValueError('Only known public JPEG data URLs can be projected')
                        data=base64.b64decode(item[len(prefix):],validate=True);digest=_bytes_sha(data)
                        source=image_paths[digest]
                        result[key]=dict(encoding='data:image/jpeg;base64',
                            path=os.path.relpath(source,packet),sha256=digest,bytes=len(data))
                    else:result[key]=project(item,item_index)
                return result
            if isinstance(value,list):return [project(v,item_index) for v in value]
            return value
        projection=[project(item,index) for index,item in enumerate(augmented)]
        manifest=dict(schema=VERSION, decision_index=self._decision_index, request_label=request_label,
            current=self._source_description(current), previous=None if previous is None else self._source_description(previous),
            first_public_bilateral_reference=None if reference is None else self._source_description(reference),
            current_observation_is_duplicate_id=duplicate, first_reference_selected_this_observation=selected_contact,
            first_reference_selection='First distinct public observation with both finite finger_contact_N >0.02N; not persistence, grasp success or object truth',
            historical_references=historical_records, historical_images_inserted=len(candidates),
            total_image_count=2+len(candidates), expanded_input=expanded,
            current_user_item_preserved=True, current_user_item_index=len(augmented)-1,
            input_items_public_projection=projection,
            full_wire_input_canonical_sha256=canonical_hash(augmented),
            exact_full_input_reconstructable=not redactions, private_provider_items_redacted=redactions,
            public_projection_canonical_sha256=canonical_hash(projection),
            private_reasoning_credentials_headers_saved=False,
            source_scope='Only already-encoded public RGB, robot/tactile/time and public wrist calibration; no environment/object truth/teacher stages',
            no_action_or_success_label_generated=True,
            budget_scope='Augmented input delegated before the unchanged client computes token bound/reserves shared ledger; no extra network request')
        (packet/'input_items_manifest.json').write_bytes(_json_bytes(manifest))
        return packet
