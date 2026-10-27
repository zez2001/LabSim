"""Stdlib-only GPT07 public-artifact verification; no simulator or network."""
import base64
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main():
    source=read(BASE/'manifest.json');summary=read(BASE/'summary.json')
    for row in source['copied_files']:
        path=(BASE/row['path']).resolve();assert path.is_relative_to(BASE)
        assert sha(path)==row['SHA256'] and path.stat().st_size==row['bytes']
    full=0;images=0;redactions=0;observations=sorted((BASE/'gpt_control/observations').glob('decision_*'))
    for index,folder in enumerate(observations):
        packet_dir=BASE/'gpt_control/temporal_visual_context'/folder.name
        packet=read(packet_dir/'input_items_manifest.json');projection=packet['input_items_public_projection']
        assert packet['decision_index']==index and packet['current_user_item_index']==len(projection)-1
        assert canonical(projection)==packet['public_projection_canonical_sha256']
        assert len(projection[-1]['content'])==5
        assert projection[-1]['content'][0]['text']==(folder/'public_observation.json').read_text()
        assert packet['total_image_count']==3+len(packet['historical_references'])<=4
        assert packet['historical_input_policy']['max_images']==1
        assert sha(packet_dir/'pre_detail_input_items_manifest.json')==packet['pre_detail_manifest']['sha256']
        assert read(packet_dir/'pre_detail_preparation.json')['API_sent'] is False
        def restore(value):
            if isinstance(value,list):return [restore(child) for child in value]
            if isinstance(value,dict):
                result={}
                for key,child in value.items():
                    if key=='image_url' and isinstance(child,dict):
                        path=(packet_dir/child['path']).resolve();assert path.is_relative_to(BASE)
                        data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==child['sha256']
                        result[key]='data:image/jpeg;base64,'+base64.b64encode(data).decode()
                    else:result[key]=restore(child)
                return result
            return value
        rebuilt=restore(projection)
        if packet['exact_full_input_reconstructable']:
            assert not packet['private_provider_items_redacted']
            assert canonical(rebuilt)==packet['full_wire_input_canonical_sha256'];full+=1
        else:assert packet['private_provider_items_redacted']
        detail=packet['fixed_side_detail']['metadata']
        assert sha(folder/'side_camera.jpg')==detail['source_encoded_side_jpeg_sha256']
        assert sha(packet_dir/'current_side_detail.jpg')==detail['derived_jpeg_sha256']
        assert detail['transmitted_resolution_wh']==[480,480] and detail['roi_pixel_edges_xyxy']==[240,32,520,312]
        A,K=detail['transmitted_pixel_from_source_pixel'],detail['intrinsic_matrix_source']
        product=[[sum(A[i][k]*K[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        assert product==detail['intrinsic_matrix_detail']
        redactions+=len(packet['private_provider_items_redacted']);images+=packet['total_image_count']
    counts=summary['actual_counts'];assert len(observations)==counts['public_observation_preparations']==46
    assert full==counts['full_input_items_reconstructable_decisions']==8
    assert redactions==counts['private_redactions']==38 and images==182
    actions=read(BASE/'action_sequence.json');assert len(actions)==46 and actions[-1]['tool']=='finish'
    receipts=[row['receipt'] for row in actions if row.get('receipt') and 'executed_control_ticks' in row['receipt']]
    assert len(receipts)==45 and sum(row['executed_control_ticks'] for row in receipts)==5400
    assert sum(row['executed_physics_steps'] for row in receipts)==21600
    assert abs(sum(row['executed_duration_s'] for row in receipts)-90)<1e-9
    labels=summary['original_labels'];assert labels['task_success'] is False and labels['failure_type']=='TASK_INCOMPLETE'
    assert labels['grasp_success'] is True and labels['source_slot_cleared'] is True and labels['transport_success'] is True
    assert labels['post_retreat_window']['status']=='unavailable' and labels['stable_after_retreat'] is None
    budget=summary['budget'];assert len(budget['episode_attempts'])==46
    assert sum(row['status']=='PROVIDER_TIMEOUT' for row in budget['episode_attempts'])==0
    print(json.dumps(dict(verified=True,observations=46,current_JPEGs=92,derived_JPEGs=46,
        decision_image_blocks=182,initiated_attempt_image_blocks=182,API_decisions=46,network_attempts=46,
        private_items_reconstructed=False,full_public_input_items_rebuilt=8,
        final_finish_is_not_task_success=True,network_calls_by_verifier=0)))


if __name__=='__main__':main()
