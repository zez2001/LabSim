"""CPU-only checks for the one-episode grant and exact ledger identity join."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('debug04_formal_metrics',
    Path(__file__).resolve().parents[1]/'docs/lab_cuvette_loading/Gpt_debug04_v1/tools/collect_formal_metrics.py')
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)


def inputs():
    old = dict(attempts=[dict(label='policy:historical:0:decision0', charged_estimate_usd=2., status='OK')])
    grant = dict(base_attempt_count=1, base_estimated_usd=2., additional_estimated_usd=20.,
        additional_network_attempts=480)
    current = dict(max_estimated_usd=22., max_requests=481, attempts=old['attempts']+[
        dict(label='policy:actual:0:decision0', charged_estimate_usd=.1, request_id='new', status='OK')])
    return old, grant, current


def test_only_exact_new_uuid_after_immutable_base_is_charged():
    old, grant, current = inputs()
    value = metrics.check_ledger(current, old, grant, 'actual')
    assert value['estimated_usd'] == .1 and value['new_network_attempts'] == 1
    assert value['selected_attempt_indices_zero_based'] == [1]
    assert value['historical_requests_charged_to_new_episode'] == 0
    assert value['remaining_authorized_network_attempts'] == 479


@pytest.mark.parametrize('change,match', [
    ('prefix','Historical ledger prefix'), ('foreign','foreign new requests'),
    ('cap','USD cap'), ('requests','network-attempt cap'), ('unfinished','unfinished request')])
def test_scope_or_cap_differences_are_refused(change, match):
    old, grant, current = inputs()
    if change == 'prefix':
        current['attempts'][0] = dict(current['attempts'][0], charged_estimate_usd=3.)
    elif change == 'foreign':
        current['attempts'][-1]['label'] = 'policy:other:0:decision0'
    elif change == 'cap':
        current['max_estimated_usd'] = 23.
    elif change == 'requests':
        current['max_requests'] = 482
    elif change == 'unfinished':
        current['attempts'][-1]['status'] = 'RESERVED'
    with pytest.raises(ValueError, match=match):
        metrics.check_ledger(current, old, grant, 'actual')


def test_active_run_refuses_before_reading_episode_or_creating_output(tmp_path):
    auth = tmp_path/'authorization.json'
    auth.write_text(json.dumps(dict(approved=True, maximum_formal_episodes=1)))
    output = tmp_path/'new_output'
    with pytest.raises(ValueError, match='must be closed first'):
        metrics.collect(tmp_path/'active_run', auth, tmp_path/'nonexistent_closure.json', output)
    assert not output.exists()


def test_overwrite_is_refused_before_any_source_access(tmp_path):
    output = tmp_path/'existing'
    output.mkdir()
    with pytest.raises(FileExistsError):
        metrics.collect(tmp_path/'missing', tmp_path/'missing', tmp_path/'missing', output)


def test_legacy_saved_packets_bind_actual_requests_without_inventing_full_wire(tmp_path):
    common = metrics.helper()
    root = tmp_path/'gpt_control'
    for index, label in [(0,'sent'), (1,'prepared_only')]:
        folder = root/'observations'/f'decision_{index:06d}'
        folder.mkdir(parents=True)
        public = folder/'public_observation.json'
        public.write_text(json.dumps(dict(episode_id='actual',observation_id=str(index),task_language='task')))
        jpeg = folder/'side_camera.jpg'
        jpeg.write_bytes(b'exact already encoded test bytes')
        def entry(path):
            return dict(path=path.relative_to(root).as_posix(),sha256=common.sha(path),bytes=path.stat().st_size)
        (folder/'manifest.json').write_text(json.dumps(dict(request_label=label,episode_id='actual',
            observation_id=str(index),public_observation=entry(public),images=[entry(jpeg)])))
    value = metrics.legacy_current_inputs(common,tmp_path,dict(attempts=[dict(label='sent')]))
    assert value['prepared_packet_count'] == 2 and value['actually_sent_packet_count'] == 1
    assert value['last_actual_model_packet']['request_label'] == 'sent'
    assert value['last_prepared_model_packet']['network_attempted'] is False
    assert value['first_actual_model_packet']['full_wire_input_canonical_sha256'] is None
    assert value['first_policy_observation']['observation_id'] == '0'
