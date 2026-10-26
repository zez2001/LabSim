"""CPU-only encoder/sidecar/network-double checks; no API, Isaac or motion."""
import base64
import copy
import hashlib
import io
import json

import numpy as np
from PIL import Image
import pytest

from demos.lab_cuvette_project_v1_1.camera_audit import (
    PROFILES, TeacherCameraAudit, compare_preview_requests, load_preview_contents,
)
from policy.backends.cubence import ProviderError


class PublicFacade:
    def __init__(self):
        self.calls = 0
        yy, xx = np.indices((480, 640))
        self.rgb = np.stack([xx % 256, yy % 256, (xx + yy) % 256], axis=-1).astype(np.uint8)

    def observe(self):
        self.calls += 1
        return dict(episode_id='episode', observation_id='episode:60', step_index=60,
            simulation_time=1., images={'side_camera': self.rgb, 'wrist_camera': self.rgb[:, ::-1].copy()},
            joint_positions=[0.] * 9, joint_velocities=[0.] * 9,
            TCPpose=dict(position_m=[0., 0., 1.], quaternion_wxyz=[1., 0., 0., 0.]),
            camera_meta={name: dict(intrinsic_matrix_native=[[400., 0., 320.], [0., 400., 240.], [0., 0., 1.]],
                resolution_wh=[640, 480], sensor_rendering_time_s=1.) for name in ('side_camera', 'wrist_camera')},
            phase='GT_PHASE_SENTINEL', debug={'object_xyz': [9., 9., 9.]}, object_position_m=[9., 9., 9.])


def stage(tmp_path):
    facade = PublicFacade()
    audit = TeacherCameraAudit(tmp_path / 'teacher_camera_audit')
    result = audit.capture_if_phase_changed(facade, 'GRASP')
    return facade, audit, result, audit.output / 'stage_000000'


def test_one_public_frame_yields_lossless_native_and_two_exact_encoder_previews(tmp_path):
    facade, audit, result, folder = stage(tmp_path)
    assert facade.calls == 1
    assert result['api_sent'] is False
    assert result['reviewer_phase'] == 'GRASP'
    assert result['evidence_kind'] == 'teacher_encoded_preview'
    assert np.array_equal(np.asarray(Image.open(folder / 'native_rgb/side_camera.png')), facade.rgb)
    assert audit.capture_if_phase_changed(facade, 'GRASP') is None
    assert facade.calls == 1
    for profile, wh in [('512low', (512, 384)), ('640high', (640, 480))]:
        contents = load_preview_contents(folder, profile)
        public = json.loads(contents[0]['text'])
        assert not {'phase', 'debug', 'object_position_m'} & set(public)
        assert 'GT_PHASE_SENTINEL' not in contents[0]['text']
        assert public['model_image_transforms']['side_camera']['crop'] is None
        assert public['model_image_transforms']['side_camera']['detail'] == PROFILES[profile]['detail']
        for index, name in enumerate(('side_camera', 'wrist_camera')):
            data = base64.b64decode(contents[2 + index * 2]['image_url'].split(',', 1)[1])
            saved = folder / profile / 'observations/decision_000000' / (name + '.jpg')
            assert data == saved.read_bytes()
            assert Image.open(io.BytesIO(data)).size == wh
            assert hashlib.sha256(data).hexdigest() == public['model_image_transforms'][name]['transmitted_jpeg_sha256']
        scale = wh[0] / 640
        assert public['model_image_transforms']['side_camera']['intrinsic_matrix_transmitted'][0][2] == pytest.approx((320.5 * scale) - .5)


def test_repeated_phase_deduplicated_but_terminal_frame_explicit_and_no_overwrite(tmp_path):
    facade, audit, _, _ = stage(tmp_path)
    audit.capture_if_phase_changed(facade, 'EXTRACT')
    audit.capture(facade, 'EXTRACT', event='terminal')
    assert facade.calls == 3
    index = json.loads((audit.output / 'audit.json').read_text())
    assert [s['reviewer_phase'] for s in index['snapshots']] == ['GRASP', 'EXTRACT', 'EXTRACT']
    assert index['snapshots'][-1]['reviewer_event'] == 'terminal'
    with pytest.raises(FileExistsError):
        TeacherCameraAudit(audit.output)


def test_tampered_input_rejected_before_comparison_request(tmp_path):
    _, _, _, folder = stage(tmp_path)
    image = folder / '640high/observations/decision_000000/wrist_camera.jpg'
    image.write_bytes(image.read_bytes() + b'tampered')
    client = FakeClient()
    with pytest.raises(ValueError, match='SHA256'):
        compare_preview_requests(client, folder, tmp_path / 'comparison')
    assert client.calls == []


class LedgerDouble:
    def __init__(self): self.count = 0
    def summary(self): return dict(total_network_attempts=self.count, total_estimated_usd=self.count * .01)


class FakeClient:
    def __init__(self, error=None):
        self.cfg = dict(model='gpt-6-astra', episode_timeout_s=1800, reasoning_effort='low')
        self.ledger = LedgerDouble()
        self.calls = []
        self.error = error

    def request(self, payload, **kwargs):
        self.calls.append((copy.deepcopy(payload), kwargs))
        self.ledger.count += 1
        if self.error:
            raise ProviderError(self.error)
        return dict(model='gpt-6-astra', id='response', usage=dict(input_tokens=20, output_tokens=10),
            output=[dict(type='message', content=[dict(type='output_text', text='Visible rack; the seat is occluded.')])]), dict(request_id='request')


def test_optional_comparison_uses_saved_wire_bytes_no_tools_no_retries_shared_ledger(tmp_path):
    _, _, original, folder = stage(tmp_path)
    client = FakeClient()
    result = compare_preview_requests(client, folder, tmp_path / 'comparison')
    assert len(client.calls) == 2
    assert result['budget_before']['total_network_attempts'] == 0
    assert result['budget_after']['total_network_attempts'] == 2
    assert result['robot_actions_executed'] == 0
    for (profile, probe), (payload, kwargs) in zip(result['probes'].items(), client.calls):
        assert kwargs['allow_retry'] is False
        assert kwargs['endpoint'] == 'responses'
        assert 'tools' not in payload
        assert payload['store'] is False and payload['max_output_tokens'] == 256
        assert payload['input'][0]['content'] == load_preview_contents(folder, profile)
        assert probe['api_sent'] is True and probe['network_attempts'] == 1
        assert probe['returned_model'] == 'gpt-6-astra'
        assert 'GRASP' not in json.dumps(payload)
        assert 'GT_PHASE_SENTINEL' not in json.dumps(payload)
    assert json.loads((folder / 'stage.json').read_text()) == original
    with pytest.raises(FileExistsError):
        compare_preview_requests(client, folder, tmp_path / 'comparison')


def test_comparison_retains_safe_provider_errors_without_raw_bodies(tmp_path):
    _, _, _, folder = stage(tmp_path)
    result = compare_preview_requests(FakeClient(error='RETURNED_MODEL_MISSING'), folder, tmp_path / 'comparison')
    assert all(p['status'] == 'RETURNED_MODEL_MISSING' for p in result['probes'].values())
    assert all(p['network_attempts'] == 1 for p in result['probes'].values())
    assert not any('output_text' in p for p in result['probes'].values())


def test_unsupported_profile_and_invalid_output_bound_do_not_request(tmp_path):
    _, _, _, folder = stage(tmp_path)
    client = FakeClient()
    with pytest.raises(ValueError, match='two declared'):
        load_preview_contents(folder, 'unknown')
    with pytest.raises(ValueError, match='bounded'):
        compare_preview_requests(client, folder, tmp_path / 'comparison', max_output_tokens=1000)
    assert not client.calls
