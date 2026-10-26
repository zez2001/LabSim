"""Stdlib-only byte/SHA and public payload verification; never sends a request."""
import base64
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def read(relative):
    return json.loads((BASE / relative).read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()

def main():
    copied = read('source_and_copy_manifest.json')
    for item in [*copied['source_files'], copied['provider_config']]:
        path = (BASE / item['destination']).resolve()
        assert path.is_relative_to(BASE), 'Copy path escapes compact evidence'
        assert sha(path) == item['SHA256'], 'Copied artifact hash mismatch'
    summary = read('qa_summary.json')
    path = (BASE / summary['prepared_input_manifest']).resolve()
    assert path.is_relative_to(BASE)
    record = json.loads(path.read_text())
    assert record['exact_full_input_reconstructable']
    assert not record['private_provider_items_redacted']
    def walk(value):
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'image_url' and isinstance(item, dict):
                    assert item['encoding'] == 'data:image/jpeg;base64'
                    image = (path.parent / item['path']).resolve()
                    assert image.is_relative_to(BASE), 'JPEG path escapes evidence'
                    data = image.read_bytes()
                    assert hashlib.sha256(data).hexdigest() == item['sha256']
                    result[key] = 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')
                else:
                    result[key] = walk(item)
            return result
        return value
    items = walk(record['input_items_public_projection'])
    assert canonical(items) == summary['full_wire_input_canonical_sha256']
    assert len(items) == 2 and len(items[-1]['content']) == 5
    assert sum(block.get('type') == 'input_image' for item in items
        for block in item['content']) == 4
    assert json.loads(items[-1]['content'][0]['text'])['observation_id'] == summary['current']['observation_id']
    cfg = read('provider_config.json')
    instructions = (BASE / 'observation_qa_instructions.txt').read_text()
    assert sha(BASE / 'observation_qa_instructions.txt') == summary['instructions_SHA256']
    payload = dict(model=cfg['model'], input=items, instructions=instructions,
        max_output_tokens=int(cfg['max_output_tokens']), store=False)
    if cfg.get('reasoning_effort'):
        payload['reasoning'] = dict(effort=cfg['reasoning_effort'])
    assert canonical(payload) == summary['wire_payload_canonical_sha256']
    assert 'tools' not in payload and 'tool_choice' not in payload
    ledger = read('ledger_actual_request_and_prefix.json')['request_entry']
    visible = read('visible_response.json')
    assert ledger['request_id'] == summary['request_id'] == visible['request_id']
    assert ledger['label'] == summary['request_label'] and ledger['retry_index'] == 0
    assert ledger['status'] == 'OK' and ledger['http_status'] == 200
    assert ledger['requested_model'] == ledger['returned_model'] == cfg['model']
    assert ledger['usage'] == summary['usage'] == visible['usage']
    assert summary['actual_network_attempts'] == summary['ledger_attempt_delta'] == 1
    assert summary['API_sent'] is True and summary['task_executed'] is False
    assert summary['task_success'] is None and summary['task_dataset_eligible'] is False
    print(json.dumps(dict(verified=True, exact_JPEGs=4, actual_historical_request_attempts=1,
        input_items_SHA256=canonical(items), Responses_payload_SHA256=canonical(payload),
        network_calls_by_verifier=0, task_executed_by_verifier=False)))

if __name__ == '__main__':
    main()
