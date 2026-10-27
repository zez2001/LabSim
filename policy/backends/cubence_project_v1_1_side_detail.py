"""Opt-in fixed side-JPEG magnification, with no robot or scene-state logic.

P4/P6 runners and the temporal helper remain unchanged.  This subclass adds
one current derived JPEG before the original final current observation item.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile

from PIL import Image, __version__ as PILLOW_VERSION

from .cubence import ProviderError, canonical_hash, input_token_bound, load_config
from .cubence_tools import run_episode as _run_episode, tool_definitions
from .cubence_project_v1_1_tools import (
    SYSTEM_PROMPT as P4_PROMPT, TEMPORAL_SYSTEM_PROMPT as P6_PROMPT,
    TEMPORAL_VISUAL_PROMPT, ProjectV11TemporalRobotTools)
from .cubence_project_v1_1_visual_context import (
    PublicTemporalVisualClient, _json_bytes, _public_snapshot,
    reconstruct_input_items, validate_visual_context)

VERSION = 'Project_v1_1.fixed_public_side_detail.v1'
FIXED_SIDE_DETAIL = dict(
    enabled=True, camera_name='side_camera', expected_resolution_wh=[640, 480],
    roi_pixel_edges_xyxy=[240, 32, 520, 312], max_side_px=480,
    jpeg_quality=60, detail='high', resize_interpolation='lanczos',
    max_historical_wrist_images=1,
    history_priority=['first_public_bilateral_wrist', 'previous_distinct_wrist'],
    current_reference_is_not_duplicated=True,
    expected_physical_parent='/World',
    expected_local_position_m=[-.7, -.85, 1.32],
    expected_local_quaternion_wxyz=[.72224223613739, .5659829784132289,
        -.24520192217047324, -.3128984465440159],
    mounting_tolerance=1e-5)

DETAIL_PROMPT = """
P7: CURRENT 480-by-480 side detail is a fixed crop/magnification, same exposure, with no new resolution or accuracy. Use its A/new K with current side extrinsics. Check the whole wrist, palm, fingers, held vessel and terminal arm segment against upright obstacles/open lid across views; TCP clearance or perspective overlap cannot prove 3D clearance. If unclear, observe/finish instead of moving blindly. Original CURRENT JSON/two images stay last; use its action IDs. All P6 rules remain.
At most one historical wrist is supplied: first public bilateral reference, else previous distinct; no duplicate if the reference is CURRENT.
"""
SYSTEM_PROMPT = P6_PROMPT + DETAIL_PROMPT
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail.json'


def validate_fixed_side_detail(config):
    if validate_visual_context(config) is None:
        raise ProviderError('PROTOCOL_FIXED_SIDE_DETAIL_REQUIRES_TEMPORAL_CONFIG')
    if config.get('max_context_messages') != 2:
        raise ProviderError('PROTOCOL_FIXED_SIDE_DETAIL_REQUIRES_CONTEXT2')
    value = config.get('fixed_side_detail')
    if not isinstance(value, dict) or value != FIXED_SIDE_DETAIL or value.get('enabled') is not True:
        raise ProviderError('PROTOCOL_INVALID_FIXED_SIDE_DETAIL_CONFIG')
    return copy.deepcopy(value)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _matmul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def derive_fixed_detail(current, spec):
    """Decode an existing public JPEG; source bytes are never overwritten."""
    try:
        meta = current['state']['camera_meta']['side_camera']
        if meta.get('physical_parent') != spec['expected_physical_parent']:
            raise ValueError('Different camera parent')
        p, q = meta['local_pose_position_m'], meta['local_pose_quaternion_wxyz']
        expected_q = spec['expected_local_quaternion_wxyz']
        if (len(p) != 3 or len(q) != 4 or
                not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in p+q)):
            raise ValueError('Invalid mounting')
        tolerance = spec['mounting_tolerance']
        if max(abs(a-b) for a, b in zip(p, spec['expected_local_position_m'])) > tolerance:
            raise ValueError('Different side mounting')
        if min(max(abs(a-b) for a, b in zip(q, expected_q)),
                max(abs(a+b) for a, b in zip(q, expected_q))) > tolerance:
            raise ValueError('Different side orientation')
        source = current['images']['side_camera']['jpeg']
        transform = current['state']['model_image_transforms']['side_camera']
        source_K = transform['intrinsic_matrix_transmitted']
        if (len(source_K) != 3 or any(len(row) != 3 for row in source_K)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for row in source_K for v in row)
                or source_K[0][0] <= 0 or source_K[1][1] <= 0
                or source_K[2] != [0, 0, 1]):
            raise ValueError('Invalid camera intrinsic matrix')
        with Image.open(io.BytesIO(source)) as image:
            image.load()
            if list(image.size) != spec['expected_resolution_wh'] or image.format != 'JPEG':
                raise ValueError('Different source resolution/encoding')
            x0, y0, x1, y1 = spec['roi_pixel_edges_xyxy']
            cropped = image.convert('RGB').crop((x0, y0, x1, y1))
            scale = spec['max_side_px']/max(cropped.size)
            size = (round(cropped.width*scale), round(cropped.height*scale))
            resized = cropped.resize(size, Image.Resampling.LANCZOS)
            encoded = io.BytesIO()
            resized.save(encoded, format='JPEG', quality=spec['jpeg_quality'])
        sx, sy = size[0]/(x1-x0), size[1]/(y1-y0)
        pixel = [[sx, 0., sx*(.5-x0)-.5],
                 [0., sy, sy*(.5-y0)-.5], [0., 0., 1.]]
        raw = encoded.getvalue()
        detail = dict(schema=VERSION, image_role='CURRENT_FIXED_SIDE_DETAIL',
            episode_id=current['episode_id'], observation_id=current['observation_id'],
            simulation_time_s=current['time_s'], same_camera_as='side_camera',
            source_encoded_side_jpeg_sha256=_sha(source),
            source_resolution_wh=spec['expected_resolution_wh'],
            roi_pixel_edges_xyxy=spec['roi_pixel_edges_xyxy'],
            roi_semantics='Fixed half-open pixel-array edges, no object tracking',
            transmitted_resolution_wh=list(size), scale_xy=[sx, sy],
            transmitted_pixel_from_source_pixel=pixel,
            intrinsic_matrix_source=source_K,
            intrinsic_matrix_detail=_matmul(pixel, source_K),
            pixel_convention='zero-based pixel-centre indices: dst=(src-roi_origin+.5)*scale-.5',
            source_jpeg_reencoded_or_modified=False, new_sensor_measurement=False,
            no_physical_or_image_resolution_gain=True, jpeg_quality=spec['jpeg_quality'],
            detail=spec['detail'], resize_interpolation='Pillow LANCZOS',
            Pillow_version=PILLOW_VERSION, derived_jpeg_sha256=_sha(raw),
            derived_jpeg_bytes=len(raw))
        return raw, detail
    except (KeyError, ValueError, TypeError, OSError, OverflowError):
        raise ProviderError('PROTOCOL_FIXED_SIDE_DETAIL_CAMERA_OR_IMAGE_MISMATCH') from None


class PublicFixedSideDetailClient(PublicTemporalVisualClient):
    """The unchanged temporal state machine plus one fixed current image."""
    def __init__(self, client, output):
        self.detail_config = validate_fixed_side_detail(client.cfg)
        super().__init__(client, output)

    def _save_packet(self, augmented, current, previous, reference, candidates,
                     duplicate, selected_contact, request_label, expanded):
        original_candidates = candidates
        selected = next((item for item in candidates
            if 'first_public_bilateral_wrist' in item['roles']), None)
        if selected is None and reference is None:
            selected = next((item for item in candidates
                if 'previous_distinct_wrist' in item['roles']), None)
        candidates = [] if selected is None else [selected]
        if original_candidates:
            # The base temporal helper inserted exactly one historical user
            # group immediately before CURRENT. Only this new P7 policy filters
            # it; the helper and P6 default are unchanged.
            historical = augmented[-2]
            assert historical['role'] == 'user'
            assert historical['content'][0]['text'].startswith('HISTORICAL PUBLIC WRIST REFERENCES')
            if selected is None:
                augmented.pop(-2)
            else:
                offset = original_candidates.index(selected)
                historical['content'] = [historical['content'][0],
                    *historical['content'][1+2*offset:3+2*offset]]
        packet = super()._save_packet(augmented, current, previous, reference,
            candidates, duplicate, selected_contact, request_label, bool(candidates))
        path = packet/'input_items_manifest.json'
        before = path.read_bytes()
        with (packet/'pre_detail_input_items_manifest.json').open('xb') as stream:
            stream.write(before)
        (packet/'pre_detail_preparation.json').write_bytes(_json_bytes(dict(
            schema=VERSION, status='intermediate_preparation_not_actual_input',
            API_sent=False, pre_detail_manifest_SHA256=_sha(before))))
        record = json.loads(before)
        image, detail = derive_fixed_detail(current, self.detail_config)
        with (packet/'current_side_detail.jpg').open('xb') as stream:
            stream.write(image)
        (packet/'current_side_detail.json').write_bytes(_json_bytes(detail))
        public_caption = dict(episode_id=detail['episode_id'], observation_id=detail['observation_id'],
            simulation_time_s=detail['simulation_time_s'], same_camera_as='side_camera',
            source_sha256=detail['source_encoded_side_jpeg_sha256'], derived_sha256=detail['derived_jpeg_sha256'],
            roi_xyxy=detail['roi_pixel_edges_xyxy'], output_wh=detail['transmitted_resolution_wh'],
            A=detail['transmitted_pixel_from_source_pixel'], K=detail['intrinsic_matrix_detail'])
        text = 'CURRENT FIXED SIDE DETAIL\n'+json.dumps(public_caption,
            ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        image_block = dict(type='input_image',
            image_url='data:image/jpeg;base64,'+base64.b64encode(image).decode('ascii'),
            detail=self.detail_config['detail'])
        group = dict(role='user', content=[dict(type='input_text', text=text), image_block])
        index = len(augmented)-1
        augmented.insert(index, group)
        assert augmented[-1]['content'] == current['source_contents']
        projected = copy.deepcopy(group)
        projected['content'][1]['image_url'] = dict(encoding='data:image/jpeg;base64',
            path='current_side_detail.jpg', sha256=_sha(image), bytes=len(image))
        projection = record['input_items_public_projection']
        projection.insert(index, projected)
        redactions = copy.deepcopy(record['private_provider_items_redacted'])
        for redaction in redactions:
            if redaction['input_item_index'] >= index:
                redaction['input_item_index'] += 1
        record.update(schema=VERSION, base_temporal_schema=record['schema'],
            pre_detail_manifest=dict(path='pre_detail_input_items_manifest.json',
                sha256=_sha(before), scope='Intermediate preparation; never delegated alone'),
            fixed_side_detail=dict(metadata=detail, image_path='current_side_detail.jpg',
                metadata_path='current_side_detail.json', source='Current public side JPEG only'),
            historical_input_policy=dict(max_images=1,
                priority=self.detail_config['history_priority'],
                no_current_reference_duplication=True,
                reference_exists=reference is not None,
                base_candidate_roles=[item['roles'] for item in original_candidates],
                supplied_roles=[item['roles'] for item in candidates],
                omitted_roles=[item['roles'] for item in original_candidates if item is not selected]),
            total_image_count=record['total_image_count']+1,
            current_user_item_index=len(augmented)-1, current_user_item_preserved=True,
            fixed_detail_user_item_index=index, expanded_input=True,
            input_items_public_projection=projection,
            public_projection_canonical_sha256=canonical_hash(projection),
            full_wire_input_canonical_sha256=canonical_hash(augmented),
            private_provider_items_redacted=redactions,
            budget_scope='Final3–4 images delegated once before unchanged client bounds/reserves the shared ledger; no additional API call',
            source_scope='Original public RGB/robot/tactile/calibration plus fixed magnification; no object/seat/teacher state')
        path.write_bytes(_json_bytes(record))
        return packet


class ProjectV11FixedSideDetailTools(ProjectV11TemporalRobotTools):
    @staticmethod
    def controller_metadata():
        value = ProjectV11TemporalRobotTools.controller_metadata()
        value.update(tools_class='ProjectV11FixedSideDetailTools',
            prompt_version='Project_v1_1.public_tools.v7_fixed_side_detail',
            tool_response_memory_scope='Opt-in P7 profile: latest one complete response/tool-receipt turn (max_context_messages=2); P6 context4 unchanged',
            fixed_side_detail_version=VERSION,
            fixed_side_detail_profile=copy.deepcopy(FIXED_SIDE_DETAIL),
            historical_input_policy=dict(max_images=1,
                priority=FIXED_SIDE_DETAIL['history_priority'],
                no_current_reference_duplication=True),
            fixed_side_detail_scope='Fixed public side JPEG crop/magnification only; no new sensing, precision, detector or action')
        value['implementation_sha256'][Path(__file__).name] = _sha(Path(__file__).read_bytes())
        return value


def run_episode(environment, client, output, *, max_calls=160, prompt=None):
    """Opt-in runner; shared _run_episode avoids the P6 dispatch recursion."""
    validate_fixed_side_detail(client.cfg)
    if prompt is None or prompt in (P4_PROMPT, P6_PROMPT):
        actual_prompt = SYSTEM_PROMPT
    else:
        actual_prompt = prompt+TEMPORAL_VISUAL_PROMPT+DETAIL_PROMPT
    return _run_episode(environment, PublicFixedSideDetailClient(client, output),
        output, max_calls=max_calls, prompt=actual_prompt,
        tools_class=ProjectV11FixedSideDetailTools)


class _Capture:
    def __init__(self, cfg):
        self.cfg, self.ledger, self.last_input, self.calls = cfg, None, None, 0
    def responses(self, items, **kwargs):
        self.last_input = copy.deepcopy(items)
        self.calls += 1
        return None


def _closed_source_proof(source, proof_path):
    proof = json.loads(proof_path.read_text())
    if (proof.get('process_exited') is not True or proof.get('exit_code') != 0
            or not isinstance(proof.get('pid'), int) or isinstance(proof.get('pid'), bool)
            or proof['pid'] <= 0 or (Path('/proc')/str(proof['pid'])).exists()):
        raise ValueError('Source must have a real closed proof and absent PID')
    expected = source.parent.parent.resolve()
    identities = []
    if isinstance(proof.get('run_directory'), str):
        identities.append(Path(proof['run_directory']).resolve())
    command = proof.get('command')
    if isinstance(command, list):
        outputs = []
        for index, token in enumerate(command):
            if token == '--output':
                if index+1 >= len(command) or not isinstance(command[index+1], str) or not command[index+1]:
                    raise ValueError('Invalid source command output')
                outputs.append(command[index+1])
            elif isinstance(token, str) and token.startswith('--output='):
                outputs.append(token.split('=', 1)[1])
        if len(outputs)>1 or any(not item for item in outputs):
            raise ValueError('Closed proof does not identify an unambiguous source run')
        identities.extend(Path(item).resolve() for item in outputs)
    if not identities or any(identity != expected for identity in identities):
        raise ValueError('Closed proof does not identify the source run')
    return proof


def preview_closed_public(source, output, *, current_decision=24,
                          source_process_proof=None, provider_config=DEFAULT_PROFILE):
    """Replay public snapshots offline, retain only the final portable packet."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Refusing to overwrite fixed-detail preview')
    source_run = source.parent.parent
    if source_run.is_relative_to(output) or output.is_relative_to(source_run):
        raise ValueError('Preview must be separate from the entire source run')
    proof_path = Path(source_process_proof or source.parent.parent/'process_exit.json')
    _closed_source_proof(source, proof_path)
    if not isinstance(current_decision, int) or isinstance(current_decision, bool) or current_decision < 0:
        raise ValueError('Invalid source decision')
    cfg = load_config(provider_config)
    validate_fixed_side_detail(cfg)
    before = {str(proof_path.resolve()): _sha(proof_path.read_bytes())}
    snapshots = []
    for index in range(current_decision+1):
        folder = source/'observations'/f'decision_{index:06d}'
        text = (folder/'public_observation.json').read_text()
        manifest = json.loads((folder/'manifest.json').read_text())
        if (manifest.get('decision_index') != index or
                manifest['public_observation']['sha256'] != _sha(text.encode())):
            raise ValueError('Source public provenance mismatch')
        contents = [dict(type='input_text', text=text)]
        files = [folder/'public_observation.json', folder/'manifest.json']
        for name in ('side_camera', 'wrist_camera'):
            data = (folder/(name+'.jpg')).read_bytes()
            item = next(row for row in manifest['images'] if row['camera_name'] == name)
            if item['sha256'] != _sha(data):
                raise ValueError('Source exact JPEG mismatch')
            contents.extend([dict(type='input_text', text='Synchronized RGB: '+name),
                dict(type='input_image', image_url='data:image/jpeg;base64,'+base64.b64encode(data).decode('ascii'), detail='high')])
            files.append(folder/(name+'.jpg'))
        snapshot = _public_snapshot(contents, index, manifest['request_label'])
        if snapshots and snapshot['episode_id'] != json.loads(snapshots[0][1][0]['text'])['episode_id']:
            raise ValueError('Offline source prefix must belong to one episode')
        snapshots.append((folder, contents, manifest['request_label']))
        before.update({str(p.resolve()): _sha(p.read_bytes()) for p in files})
    with tempfile.TemporaryDirectory(prefix='labsim-fixed-side-preview-') as scratch_name:
        scratch = Path(scratch_name)
        capture = _Capture(cfg)
        client = PublicFixedSideDetailClient(capture, scratch)
        for index, (folder, contents, label) in enumerate(snapshots):
            target = scratch/'observations'/f'decision_{index:06d}'
            target.mkdir(parents=True)
            for name in ('public_observation.json', 'manifest.json', 'side_camera.jpg', 'wrist_camera.jpg'):
                shutil.copy2(folder/name, target/name)
            client.responses([dict(role='user', content=contents)],
                instructions=SYSTEM_PROMPT, tools=tool_definitions(), label=label)
        final_rel = Path('temporal_visual_context')/f'decision_{current_decision:06d}'
        final_path = scratch/final_rel/'input_items_manifest.json'
        assert reconstruct_input_items(final_path) == capture.last_input
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(scratch/final_rel, output/final_rel)
        current_rel = Path('observations')/f'decision_{current_decision:06d}'
        shutil.copytree(scratch/current_rel, output/current_rel)
        final = output/final_rel/'input_items_manifest.json'
        record = json.loads(final.read_text())
        record.update(API_sent=False, offline_preview=True, model_response_generated=False)
        final.write_bytes(_json_bytes(record))
        outcome = output/final_rel/'call_outcome.json'
        outcome.write_bytes(_json_bytes(dict(status='offline_capture_only',
            API_sent=False, model_response_generated=False)))
        (output/'provider_config.json').write_bytes(_json_bytes(cfg))
        (output/'prompt.txt').write_text(SYSTEM_PROMPT)
        items = reconstruct_input_items(final)
        payload = dict(model=cfg['model'], input=items, instructions=SYSTEM_PROMPT,
            tools=tool_definitions(), max_output_tokens=cfg['max_output_tokens'],
            parallel_tool_calls=False, store=False,
            reasoning=dict(effort=cfg['reasoning_effort']))
        summary = dict(schema=VERSION, preview=True, API_sent=False,
            actual_network_attempts=0, task_executed=False, task_success=None,
            source_process_proof=dict(path=str(proof_path.resolve()), SHA256=_sha(proof_path.read_bytes())),
            source_current_decision=current_decision,
            final_manifest=str(final.relative_to(output)),
            total_images=record['total_image_count'],
            offline_capture_calls=capture.calls, offline_calls_are_model_decisions=False,
            input_items_canonical_SHA256=canonical_hash(items),
            offline_payload_canonical_SHA256=canonical_hash(payload),
            original_client_input_token_bound=input_token_bound(payload, cfg['max_context_input_tokens']),
            source_SHA256_before=before,
            source_SHA256_after={p: _sha(Path(p).read_bytes()) for p in before},
            original_sources_unchanged=all(_sha(Path(p).read_bytes()) == h for p,h in before.items()),
            no_resolution_or_accuracy_gain=True)
        (output/'preview_summary.json').write_bytes(_json_bytes(summary))
        if not summary['original_sources_unchanged']:
            raise ValueError('Original public files changed')
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--current-decision', type=int, default=24)
    parser.add_argument('--source-process-proof', type=Path)
    parser.add_argument('--provider-config', type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args(argv)
    try:
        result = preview_closed_public(args.source, args.output,
            current_decision=args.current_decision,
            source_process_proof=args.source_process_proof, provider_config=args.provider_config)
    except (ProviderError, ValueError, OSError, KeyError, StopIteration) as error:
        parser.exit(1, 'Fixed side preview failed: '+(error.code if isinstance(error, ProviderError) else type(error).__name__)+'\n')
    print(json.dumps({k: result[k] for k in ('preview','API_sent','total_images','original_sources_unchanged')}))


if __name__ == '__main__':
    main()
