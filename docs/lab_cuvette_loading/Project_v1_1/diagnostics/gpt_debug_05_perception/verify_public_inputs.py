"""Stdlib-only verification of saved public inputs; no network or simulator."""
import base64
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def main():
    manifest = read(BASE/'manifest.json')
    for entry in manifest['copied_files']:
        path = (BASE/entry['path']).resolve()
        assert path.is_relative_to(BASE) and sha(path) == entry['SHA256']
    exact, total, redactions = 0, 0, 0
    for index in range(25):
        folder = BASE/'gpt_control/temporal_visual_context'/f'decision_{index:06d}'
        packet = read(folder/'input_items_manifest.json')
        projection = packet['input_items_public_projection']
        assert canonical(projection) == packet['public_projection_canonical_sha256']
        assert packet['current_user_item_index'] == len(projection)-1
        assert projection[-1]['role'] == 'user'
        state = json.loads(projection[-1]['content'][0]['text'])
        assert state['observation_id'] == packet['current']['observation_id']
        assert packet['total_image_count'] <= 4
        def rebuild(value):
            if isinstance(value, list):
                return [rebuild(item) for item in value]
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    if key == 'image_url' and isinstance(item, dict):
                        path = (folder/item['path']).resolve()
                        assert path.is_relative_to(BASE)
                        data = path.read_bytes()
                        assert hashlib.sha256(data).hexdigest() == item['sha256']
                        result[key] = 'data:image/jpeg;base64,'+base64.b64encode(data).decode('ascii')
                    else:
                        result[key] = rebuild(item)
                return result
            return value
        rebuilt_projection = rebuild(projection)
        if packet['exact_full_input_reconstructable']:
            assert not packet['private_provider_items_redacted']
            assert canonical(rebuilt_projection) == packet['full_wire_input_canonical_sha256']
            exact += 1
        else:
            assert packet['private_provider_items_redacted']
        total += packet['total_image_count']
        redactions += len(packet['private_provider_items_redacted'])
    original = read(BASE/'summary.json')
    assert exact == original['actual_counts']['full_input_items_reconstructable_decisions']
    assert total == 90 and redactions == 25
    final = read(BASE/'final_error_record.json')
    arguments = json.loads(final['model_tool_calls'][0]['arguments'])
    assert arguments['action_id'] == 'a25' and arguments['values'] == [.035,0,0,0,0,0]
    assert final['action_receipt']['partial_execution'] is True
    assert final['action_receipt']['executed_control_ticks'] == 114
    assert final['action_receipt']['stop_reason'] == 'ROBOT_ENVIRONMENT_COLLISION'
    print(json.dumps(dict(verified=True, actual_decisions=25,
        public_sent_image_blocks=90, full_input_reconstructable_decisions=exact,
        private_redacted_items=redactions, final_partial_receipt_preserved=True,
        network_calls_by_verifier=0, private_reasoning_reconstructed=False)))

if __name__ == '__main__':
    main()
