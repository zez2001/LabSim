"""Offline audit of restored runtime inputs and the two authorized cap changes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def environment_comparison(old_episode, episode, protocol):
    import copy
    import yaml
    old_config=yaml.safe_load((old_episode/'config.yaml').read_text())
    actual_config=yaml.safe_load((episode/'config.yaml').read_text())
    revision=protocol['environment']['HF_revision']
    roots={str(actual_config['asset_directory']).split('/assets/',1)[0],
        str(old_config['asset_directory']).split('/assets/',1)[0]}
    def normalized(value):
        if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
        if isinstance(value,list):return [normalized(v) for v in value]
        if isinstance(value,str):
            for root in roots:
                if root and value.startswith(root):return 'HF_REVISION/'+revision+value[len(root):]
        return value
    groups=('acceptance','physics','robot','gripper','control','demo_release','rack','adapter','scene',
        'geometry','cameras','executor','robot_tracking','vessel','asset_selection','source','collision_scheme')
    rows=[dict(component=key,same_after_explicit_HF_cache_root_normalization=(
        normalized(old_config.get(key))==normalized(actual_config.get(key))),
        historical_canonical_sha256=canonical(normalized(old_config.get(key))),
        actual_canonical_sha256=canonical(normalized(actual_config.get(key)))) for key in groups]
    old_state,actual_state=read(old_episode/'initial_debug.json'),read(episode/'initial_debug.json')
    state_differences=[key for key in set(old_state)|set(actual_state) if old_state.get(key)!=actual_state.get(key)]
    physical_state_keys=[key for key in set(old_state)|set(actual_state) if key!='input_geometry_compute_wall_s']
    state_checks={key:old_state.get(key)==actual_state.get(key) for key in physical_state_keys}
    old_cameras,actual_cameras=read(old_episode/'cameras.json'),read(episode/'cameras.json')
    def installations(value):
        result=copy.deepcopy(value)
        for camera in result.values():
            camera.pop('last_image_read',None)
            camera.pop('sensor_rendering_frame',None)
        return result
    same_mount=installations(old_cameras)==installations(actual_cameras)
    return dict(loaded_physical_groups=rows,normalized_HF_cache_roots=sorted(roots),
        initial_physical_state_fields_exact=all(state_checks.values()),
        initial_physical_field_equality=state_checks,initial_other_differences=state_differences,
        initial_compute_wall_difference_excluded_from_physical_identity=True,
        actual_initial_state={key:actual_state.get(key) for key in ('t','physics_step','object_position_m',
            'object_quaternion_wxyz','actual_tcp_position_m','actual_tcp_quaternion_wxyz','joints9','source_bottom_gap_m')},
        camera_installation_calibration_identical=same_mount,
        full_camera_last_render_metadata_identical=old_cameras==actual_cameras,
        camera_comparison_scope='Mounting/calibration/static fields exclude only last_image_read and sensor_rendering_frame; last-render reference frame number and pixel intensity may differ and are preserved in source files',
        overall_physical_baseline_match=all(row['same_after_explicit_HF_cache_root_normalization'] for row in rows)
            and all(state_checks.values()) and same_mount)


def audit(trial, historical_episode, output):
    trial,historical_episode,output=map(lambda p:Path(p).resolve(),(trial,historical_episode,output))
    if output.exists():
        raise FileExistsError(output)
    collector_path=Path(__file__).with_name('collect_formal_metrics.py')
    spec=importlib.util.spec_from_file_location('debug04_formal_identity_collector',collector_path)
    collector=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    common=collector.helper()
    if not common.closed_process(trial):
        raise ValueError('Identity final receipt requires actual process closure')
    episode=trial/'environment/episode_0000'
    protocol_path=trial/'environment.frozen_protocol.json'
    controller_path=episode/'gpt_control/controller.json'
    historical_controller=historical_episode/'gpt_control/controller.json'
    protocol=read(protocol_path)
    actual,old=read(controller_path),read(historical_controller)
    supervisor=read(trial/'supervisor.json')
    checkout=Path(supervisor['runtime_checkout'])
    differences={key:dict(historical=old['provider_config'].get(key),actual=actual['provider_config'].get(key))
        for key in set(actual['provider_config'])|set(old['provider_config'])
        if actual['provider_config'].get(key)!=old['provider_config'].get(key)}
    other=[key for key in set(actual)|set(old) if key!='provider_config' and actual.get(key)!=old.get(key)]
    source_checks=[]
    for relative,expected in protocol['locked_source_files'].items():
        path=checkout/relative
        actual_sha=sha(path) if path.is_file() else None
        source_checks.append(dict(path=relative,expected_sha256=expected,actual_sha256=actual_sha,
            unchanged=actual_sha==expected))
    prompt_sha=hashlib.sha256(actual['prompt'].encode()).hexdigest()
    tool_sha=canonical(actual['tool_schema'])
    physical=environment_comparison(historical_episode,episode,protocol)
    checks=dict(only_two_financial_cap_differences=set(differences)=={'max_requests','max_estimated_usd'},
        all_other_controller_fields_identical=not other,
        prompt_matches_frozen_sha=prompt_sha==protocol['prompt_sha256'],
        tool_schema_matches_frozen_sha=tool_sha==protocol['tool_schema_canonical_sha256'],
        all_frozen_runtime_source_files_unchanged=all(row['unchanged'] for row in source_checks),
        object_truth_used_false=actual.get('object_truth_used') is False,
        teacher_used_false=actual.get('teacher_used') is False,
        physics_paused_during_inference=actual.get('physics_paused_during_inference') is True,
        actual_physical_reset_configuration_and_camera_installation_match=physical['overall_physical_baseline_match'],
        financial_caps_match_actual_cumulative_ledger=(
            actual['provider_config']['max_requests']==read(protocol['ledger'])['max_requests'] and
            actual['provider_config']['max_estimated_usd']==read(protocol['ledger'])['max_estimated_usd']))
    sources={str(path):sha(path) for path in (controller_path,historical_controller,protocol_path,
        trial/'supervisor.json',episode/'result.json',episode/'gpt_control/summary.json',
        episode/'initial_debug.json',historical_episode/'initial_debug.json',episode/'config.yaml',
        historical_episode/'config.yaml',episode/'cameras.json',historical_episode/'cameras.json')}
    value=dict(schema='labsim.Gpt_debug04_v1.formal_policy_identity_audit.v1',passed=all(checks.values()),
        checks=checks,episode_id=read(episode/'result.json')['episode_id'],
        actual_execution_commit=protocol['runtime_commit'],runtime_checkout=str(checkout),
        historical_episode_id=protocol['historical_episode_id'],historical_source_commit=protocol['historical_source_commit'],
        source_sha256=sources,provider_differences=differences,other_controller_field_differences=other,
        prompt_sha256=prompt_sha,tool_schema_canonical_sha256=tool_sha,frozen_source_checks=source_checks,
        actual_vs_historical_environment=physical,
        requested_model=actual['provider_config']['model'],requested_endpoint=actual['provider_config']['endpoint'],
        actual_historical_profile_preserved=all(checks.values()),
        budget_semantics='max_requests/max_estimated_usd are cumulative limits retaining immutable historical prefix; new owner grant is 480 attempts/$20, one formal episode; task call limit remains160',
        source_mutation=False,credential_env_value_read=False,network_calls=0,
        limits='Saved current public state and wire JPEGs are available; the exact historical vendor does not save a canonical full-conversation HTTP request hash; supplier model identity and invoice are not independently verified')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial',required=True,type=Path)
    parser.add_argument('--historical-episode',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    value=audit(args.trial,args.historical_episode,args.output)
    print(json.dumps(dict(passed=value['passed'],episode_id=value['episode_id'],checks=len(value['checks']))))
    return 0 if value['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
