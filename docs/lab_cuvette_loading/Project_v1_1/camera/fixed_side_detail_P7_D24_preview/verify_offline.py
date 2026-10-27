"""Verify this offline preview's exact files without LabSim or network access."""
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def main():
    receipt = json.loads((ROOT/'artifact_manifest.json').read_text())
    for row in receipt['files']:
        path = (ROOT/row['path']).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Nonportable file reference')
        data = path.read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['SHA256'], row['path']
    summary = json.loads((ROOT/'preview_summary.json').read_text())
    path = ROOT/summary['final_manifest']
    manifest = json.loads(path.read_text())

    def restore(value):
        if isinstance(value, list):
            return [restore(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'image_url' and isinstance(item, dict):
                    image_path = (path.parent/item['path']).resolve()
                    assert image_path.is_relative_to(ROOT)
                    data = image_path.read_bytes()
                    assert sha(data) == item['sha256'] and len(data) == item['bytes']
                    result[key] = 'data:image/jpeg;base64,'+base64.b64encode(data).decode()
                else:
                    result[key] = restore(item)
            return result
        return value

    items = restore(manifest['input_items_public_projection'])
    assert canonical(items) == manifest['full_wire_input_canonical_sha256']
    assert manifest['API_sent'] is False and summary['actual_network_attempts'] == 0
    assert manifest['current_user_item_index'] == len(items)-1
    assert len(items[-1]['content']) == 5
    assert sum(block.get('type') == 'input_image' for item in items
        for block in item.get('content', []) if isinstance(block, dict)) == 4
    original = json.loads((ROOT/'observations/decision_000024/public_observation.json').read_text())
    assert json.loads(items[-1]['content'][0]['text']) == original
    detail = manifest['fixed_side_detail']['metadata']
    source = (ROOT/'observations/decision_000024/side_camera.jpg').read_bytes()
    assert sha(source) == detail['source_encoded_side_jpeg_sha256']
    assert detail['transmitted_resolution_wh'] == [480, 480]
    assert detail['roi_pixel_edges_xyxy'] == [240, 32, 520, 312]
    A, K = detail['transmitted_pixel_from_source_pixel'], detail['intrinsic_matrix_source']
    product = [[sum(A[i][k]*K[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    for row, expected in zip(product, detail['intrinsic_matrix_detail']):
        assert all(abs(a-b) < 1e-9 for a,b in zip(row,expected))
    assert manifest['historical_input_policy']['max_images'] == 1
    assert manifest['historical_input_policy']['supplied_roles'] == [['first_public_bilateral_wrist']]
    print(json.dumps(dict(verified=True, files=len(receipt['files']), images=4,
        API_sent=False, task_executed=False, original_current_item_preserved=True)))


if __name__ == '__main__':
    main()
