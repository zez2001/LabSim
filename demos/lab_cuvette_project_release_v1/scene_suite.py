"""Fixed, versioned scene definitions over the existing release environment.

The word random describes how the ten test instances were designed.  Runtime
selection reads an explicit definition; reset never samples a new layout.
This module is CPU-only and imports neither Isaac nor a model service.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE_VERSION = 'lab_cuvette_loading.scene_suite.v1'
SCENE_IDS = ('standard', *(f'random_{index:03d}' for index in range(1, 11)))
SUITE_DIRECTORY = ROOT / 'config/lab_cuvette_loading/Scene_suite_v1'
STANDARD_CONFIG = ROOT / 'config/lab_cuvette_loading/Project_release_v1/standard.yaml'
BASELINE_COMMIT = 'd54f888b7d85994fb5602a831b9ab70a30c56860'
STANDARD_CONFIG_SHA256 = '45cfd2f4361dc7a73411b727ae15e92823b0569ff03ef5d4ede4521213d4e40d'
DEPENDENCIES = (
    'config/lab_cuvette_loading/Project_release_v1/standard.yaml',
    'config/lab_cuvette_loading/V0.yaml',
    'config/lab_cuvette_loading/Project_v1/assets.lock.json',
    'demos/lab_cuvette_demo04/run.py',
    'demos/lab_cuvette_demo04/scene.py',
    'demos/lab_cuvette_demo03/scene.py',
    'demos/lab_cuvette_loading/scene.py',
    'demos/lab_cuvette_external/build.py',
    'demos/lab_cuvette_external/geometry.py',
    'demos/lab_cuvette_ext02/build.py',
    'demos/lab_cuvette_env_v1/scene.py',
    'demos/lab_cuvette_size_v1/scene.py',
    'demos/lab_cuvette_size_v1/runtime_geometry.py',
    'demos/lab_cuvette_project_v1/runtime.py',
    'demos/lab_cuvette_project_v1/geometry_audit.py',
    'demos/lab_cuvette_project_release_v1/scene_suite.py',
    'demos/lab_cuvette_project_release_v1/scene_validation.py',
    'demos/lab_cuvette_project_release_v1/scene_recording.py',
    'demos/lab_cuvette_project_release_v1/scene_data.py',
    'demos/lab_cuvette_project_release_v1/suite_runner.py',
    'demos/lab_cuvette_project_release_v1/launch.py',
    'demos/lab_cuvette_project_release_v1/environment.py',
    'demos/lab_cuvette_project_release_v1/usage_metadata.py',
    'demos/lab_cuvette_project_release_v1/contract.py',
    'data_collectors/lab_cuvette_project_release_collector.py',
    'factories/task_factory.py',
    'factories/collector_factory.py',
    'demos/lab_cuvette_project_v1_1/continuous_ik.py',
    'demos/lab_cuvette_project_v1_1/gripper_hold.py',
    'demos/lab_cuvette_project_v1_1/robot_tracking.py',
    'controllers/lab_cuvette_env_v1_controller.py',
    'controllers/lab_cuvette_project_v1_1_controller.py',
    'demos/lab_cuvette_project_v1_1/scorer.py',
    'tasks/lab_cuvette_loading_project_release.py',
)


def _plain(value):
    try:
        from omegaconf import OmegaConf
        if OmegaConf.is_config(value):
            return OmegaConf.to_container(value, resolve=True)
    except ImportError:
        pass
    return copy.deepcopy(value)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False, ensure_ascii=False).encode()).hexdigest()


def suite_scene_ids(suite='random10'):
    if suite != 'random10':
        raise ValueError('Unknown scene suite: ' + str(suite) + '; expected random10')
    return SCENE_IDS[1:]


def load_suite(*, directory=SUITE_DIRECTORY):
    value = json.loads((Path(directory)/'suite.json').read_text(encoding='utf-8'))
    if value.get('schema') != SUITE_VERSION or value.get('suite_version') != SUITE_VERSION:
        raise ValueError('Scene suite identity mismatch')
    if tuple(item.get('scene_id') for item in value.get('scenes', [])) != SCENE_IDS:
        raise ValueError('Scene suite must register exactly standard plus random_001..010 in order')
    if tuple(value.get('random10_scene_ids', [])) != SCENE_IDS[1:]:
        raise ValueError('Random-10 membership mismatch')
    return value


def validate_selection(scene_id='standard', purpose='eval'):
    if scene_id not in SCENE_IDS:
        raise ValueError('Unknown scene: ' + str(scene_id) + '; expected ' + ', '.join(SCENE_IDS))
    if purpose not in ('demo', 'collect', 'train', 'validation', 'eval', 'serve'):
        raise ValueError('Unknown scene execution purpose: ' + str(purpose))
    if scene_id != 'standard' and purpose not in ('eval', 'serve'):
        raise ValueError('Random-10 scenes are policy_evaluation only; ' + purpose + ' requires standard')
    return dict(scene_id=scene_id, suite_version=SUITE_VERSION,
                allowed_uses=['demonstration', 'training', 'policy_evaluation']
                if scene_id == 'standard' else ['policy_evaluation'])


def load_scene_definition(scene_id='standard', *, directory=SUITE_DIRECTORY):
    validate_selection(scene_id)
    path = Path(directory) / 'scenes' / (scene_id + '.json')
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('scene_id') != scene_id or value.get('suite_version') != SUITE_VERSION:
        raise ValueError('Scene definition identity mismatch: ' + str(path))
    supplied = value.get('definition_sha256')
    if supplied != canonical_sha({key: item for key, item in value.items() if key != 'definition_sha256'}):
        raise ValueError('Scene definition hash mismatch: ' + str(path))
    registry = load_suite(directory=directory)
    member = next(item for item in registry['scenes'] if item['scene_id'] == scene_id)
    if member.get('path') != 'scenes/'+scene_id+'.json' or member.get('definition_sha256') != supplied:
        raise ValueError('Scene definition differs from registered suite membership: ' + scene_id)
    return value


def _rotate_xy(value, angle_deg):
    angle = math.radians(angle_deg)
    c, s = math.cos(angle), math.sin(angle)
    x, y = value[:2]
    return [c*x-s*y, s*x+c*y, *value[2:]]


def validate_protocol_invariants(config, definition):
    """Reject a custom configuration that changes this fixed scene protocol.

    The baseline YAML is immutable. Runtime paths and provenance are allowed to
    vary; the physical, action, camera, controller and scorer numerical settings
    remain its values. Assembly coordinates may be baseline values (before
    selection) or this definition's exact effective values (idempotent reuse).
    """
    import yaml
    content = STANDARD_CONFIG.read_bytes()
    if hashlib.sha256(content).hexdigest() != STANDARD_CONFIG_SHA256:
        raise ValueError('Scene suite frozen standard source changed; create a new suite version')
    baseline = yaml.safe_load(content)
    data = _plain(config)
    expected = _apply_values(baseline, definition)
    errors = []
    for key in ('physics', 'acceptance', 'demo_release', 'cameras', 'gripper',
                'executor', 'robot_tracking', 'teacher_execution', 'geometry', 'adapter',
                'collection', 'training_scene', 'randomization'):
        if data.get(key) != baseline.get(key):
            errors.append(key)
    for key in ('asset_id', 'collision_scheme', 'task_type', 'controller_type', 'collector_type'):
        if data.get(key) != baseline.get(key):
            errors.append(key)
    for key in ('outer_xy_m', 'height_m', 'mass_kg', 'xy_scale', 'asset_id',
                'actual_outer_dimensions_m', 'center_of_mass_m', 'inertia_body_kg_m2',
                'axis_scale_from_control'):
        if data.get('vessel', {}).get(key) != baseline['vessel'].get(key):
            errors.append('vessel.'+key)
    for key, value in baseline['robot'].items():
        if key not in ('usd_path', 'initial_tcp_m', 'initial_joint_basis') and data.get('robot', {}).get(key) != value:
            errors.append('robot.'+key)
    # New numerical robot overrides such as finger_kp cannot bypass the declared
    # robot parameters merely because the baseline omitted that optional field.
    for key in data.get('robot', {}):
        if key not in baseline['robot'] and key not in ('asset_metadata',):
            errors.append('robot.'+key)
    for block, adaptable in (
        ('rack', {'origin_m', 'yaw_deg'}),
        ('scene', {'instrument_xyz_m', 'instrument_yaw_deg'}),
        ('control', {'retreat_lateral_m', 'target_vessel_yaw_deg'}),
        ('vessel', {'yaw_deg'}),
    ):
        if block == 'vessel':
            keys = {'yaw_deg'}
        else:
            keys = set(baseline[block]) | set(data.get(block, {}))
        for key in keys:
            actual = data.get(block, {}).get(key)
            original = baseline[block].get(key)
            target = expected[block].get(key)
            if key in adaptable:
                if actual != original and actual != target:
                    errors.append(block+'.'+key)
            elif actual != original:
                errors.append(block+'.'+key)
    # These settings define the original public action/observation and scoring
    # paths. Cache roots, execution intent, seed and recording knobs are omitted.
    for key in ('task_type', 'control_hz', 'physics_hz', 'policy_hz',
                'action_max_translation_m', 'action_max_rotation_rad',
                'action_max_joint_delta_rad', 'max_action_duration_s',
                'gripper_effort_max_N', 'geometry_safe_stop_above_rim_m',
                'scene_layout_module', 'scorer_module', 'geometry_audit_module',
                'material_geometry_module', 'material_geometry_check_hz',
                'render_zero_delay', 'render_flush_passes_per_control', 'probe_cooked_collision'):
        if data.get('env', {}).get(key) != baseline['env'].get(key):
            errors.append('env.'+key)
    for key in ('action_interface_version', 'scorer_version', 'executor_version',
                'camera_version', 'camera_names', 'backend_gripper_effort_N', 'public_observation'):
        if data.get('project', {}).get(key) != baseline['project'].get(key):
            errors.append('project.'+key)
    if data.get('task', {}).get('control_hz') != baseline['task']['control_hz']:
        errors.append('task.control_hz')
    def same_logical_asset(value, original):
        parts, expected_parts = Path(str(value)).parts, Path(original).parts
        return len(parts) >= len(expected_parts) and parts[-len(expected_parts):] == expected_parts
    for key in ('asset_directory', 'derived_directory', 'asset_registry'):
        if not same_logical_asset(data.get(key), baseline[key]):
            errors.append(key)
    for key in ('instrument', 'vessel', 'vessel_collision'):
        if not same_logical_asset(data.get('source', {}).get(key), baseline['source'][key]):
            errors.append('source.'+key)
    if not same_logical_asset(data.get('robot', {}).get('usd_path'), baseline['robot']['usd_path']):
        errors.append('robot.usd_path')
    if data.get('asset_selection', {}).get('asset_id') != baseline['asset_selection']['asset_id']:
        errors.append('asset_selection.asset_id')
    if errors:
        raise ValueError('Fixed scene suite protocol changed: '+', '.join(sorted(set(errors)))+
            '; use the frozen standard baseline and registered scene definition')
    return dict(passed=True, standard_configuration_sha256=STANDARD_CONFIG_SHA256,
        scope='Frozen numerical/public-interface fields and logical asset identities; actual asset content is verified by the existing resolver and geometry audit')


def _apply_values(config, definition):
    data = _plain(config)
    if definition['scene_id'] == 'standard':
        return data
    params = definition['actual_parameters']
    data['rack']['origin_m'] = params['rack']['origin_m']
    data['rack']['yaw_deg'] = params['rack']['yaw_deg']
    data['scene']['instrument_xyz_m'] = params['instrument']['origin_m']
    data['scene']['instrument_yaw_deg'] = params['instrument']['yaw_deg']
    if definition['scene_id'] != 'standard':
        # Dynamic vessel and F6 blue vessel share the rack-relative initial yaw;
        # insertion follows the selected seat's rotated frame, not that yaw.
        data['vessel']['yaw_deg'] = params['vessel_initial_yaw_deg']
        data['control']['target_vessel_yaw_deg'] = params['target_vessel_yaw_deg']
        data['control']['retreat_lateral_m'] = params['retreat_lateral_m']
        data.setdefault('release', {})['record_purpose'] = 'policy_evaluation'
    return data


def select_scene(config, scene_id='standard', *, purpose='eval'):
    """Apply one fixed instance; preserve type and frozen standard numeric fields.

    ``env.mode`` remains standard to reuse the original reset path without its
    legacy on-reset random sampler.  ``scene_suite.scene_id`` is authoritative
    for dataset use, while the independent suite fingerprint binds the layout.
    """
    membership = validate_selection(scene_id, purpose)
    definition = load_scene_definition(scene_id)
    data = _plain(config)
    previous = data.pop('scene_suite', None)
    if previous and previous.get('scene_id') != scene_id:
        raise ValueError('Scene is fixed for an environment; create a fresh environment to change it')
    if data.get('version') != 'Project_release_v1':
        raise ValueError('Scene_suite_v1 requires Project_release_v1')
    if data.get('env', {}).get('mode') != 'standard' or data.get('scene_mode') != 'standard':
        raise ValueError('Fixed suite requires the standard reset path, not legacy random sampling')
    if any(item is True for key, item in data.get('randomization', {}).items() if key.endswith('enabled')):
        raise ValueError('Fixed suite cannot enable on-reset scene randomization')
    validate_protocol_invariants(data, definition)
    data = _apply_values(data, definition)
    data['scene_suite'] = dict(membership,
        scene_definition_sha256=definition['definition_sha256'],
        source_seed=definition['source_seed'], reset_sampling_enabled=False,
        actual_parameters=definition['actual_parameters'],
        initialization_rules=definition['initialization_rules'])
    try:
        from omegaconf import OmegaConf
        if OmegaConf.is_config(config):
            return OmegaConf.create(data)
    except ImportError:
        pass
    return data


apply_scene_configuration = select_scene


def dependency_snapshot(config=None, *, root=ROOT, geometry_audit=None):
    """Supplement existing fingerprints; never rewrite historical contracts.

    LFS pointers are recorded explicitly rather than hashed as asset content.
    USD transitive layers are supplied by the existing loaded-stage audit.
    """
    root = Path(root)
    rows = {}
    for name in DEPENDENCIES:
        path = root / name
        if not path.is_file():
            rows[name] = dict(status='missing')
            continue
        content = path.read_bytes()
        rows[name] = dict(status='present', sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        if content.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            rows[name]['status'] = 'lfs_pointer_not_loaded_content'
    audit_files = (geometry_audit or {}).get('binding', {}).get('files', {})
    body = dict(schema='labsim.scene_suite.runtime_dependencies.v1', dependencies=rows,
        loaded_geometry_dependency_sha256=audit_files,
        scope='Explicit current build/control chain plus transitive USD files from loaded-stage audit; not a complete dynamic-import proof')
    if config is not None:
        data = _plain(config)
        body['scene_identity'] = data.get('scene_suite', dict(scene_id='standard', suite_version=None))
        body['asset_identity'] = {key: data.get(key) for key in ('asset_id', 'asset_selection')}
        scene_id = body['scene_identity'].get('scene_id', 'standard')
        for path in (SUITE_DIRECTORY/'suite.json', SUITE_DIRECTORY/'scenes'/(scene_id+'.json')):
            if path.is_file():
                content = path.read_bytes()
                rows[path.relative_to(ROOT).as_posix()] = dict(status='present',
                    sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
    return dict(body, dependency_fingerprint=canonical_sha(body))


def scene_manifest(config, scene_id='standard', *, geometry_audit=None):
    """Runtime sidecar with actual config and all scene identities."""
    selected = select_scene(config, scene_id, purpose='eval')
    data = _plain(selected)
    definition = load_scene_definition(scene_id)
    dependencies = dependency_snapshot(selected, geometry_audit=geometry_audit)
    body = dict(schema=SUITE_VERSION, scene_id=scene_id,
        suite_version=SUITE_VERSION, definition=definition,
        resolved_scene_sha256=canonical_sha({key: data.get(key) for key in
            ('scene', 'rack', 'robot', 'vessel', 'adapter', 'cameras', 'physics', 'geometry', 'scene_suite')}),
        dependencies=dependencies)
    return dict(body, scene_suite_fingerprint=canonical_sha(body))


def candidate_parameters(index):
    """One-time seeded, stratified design; no simulator or policy input."""
    if not 0 <= index <= 10:
        raise ValueError('Candidate index must be0..10')
    if index == 0:
        return ([0., 0.], [0., 0.], 0., 0., 1000., 'standard',
            dict(seed=0, generator=None, stratum='unchanged_standard', raw_draws=[],
                 rounding='none; frozen baseline'))
    import numpy as np
    seed = 31000+index
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = []
    def signed(low, high, digits):
        magnitude = float(rng.uniform(low, high))
        sign = int(rng.choice([-1, 1]))
        result = round(sign*magnitude, digits)
        draws.append(dict(distribution='uniform magnitude then equiprobable sign',
            low=low, high=high, raw_magnitude=magnitude, raw_sign=sign,
            decimal_places=digits, effective_value=result))
        return result
    def uniform(low, high, digits):
        value = float(rng.uniform(low, high))
        result = round(value, digits)
        draws.append(dict(distribution='uniform', low=low, high=high,
            raw_value=value, decimal_places=digits, effective_value=result))
        return result
    rack, instrument, ryaw, iyaw, intensity = [0., 0.], [0., 0.], 0., 0., 1000.
    if index in (1, 2):
        family = 'rack_translation'
        rack[index-1] = signed(.003, .006, 6)
    elif index in (3, 4):
        family = 'instrument_translation'
        instrument[index-3] = signed(.003, .006, 6)
    elif index == 5:
        family = 'rack_rotation'
        ryaw = signed(.5, 1., 4)
    elif index == 6:
        family = 'instrument_rotation'
        iyaw = signed(.5, 1., 4)
    elif index in (7, 8):
        family = 'lighting'
        intensity = uniform(900., 950., 3) if index == 7 else uniform(1050., 1100., 3)
    else:
        family = 'combined'
        rack = [uniform(-.004, .004, 6) for _ in range(2)]
        instrument = [uniform(-.004, .004, 6) for _ in range(2)]
        ryaw, iyaw = uniform(-.5, .5, 4), uniform(-.5, .5, 4)
        intensity = uniform(950., 1050., 3)
    audit = dict(seed=seed, generator='numpy.random.Generator(PCG64)',
        numpy_version=np.__version__, stratum=family, raw_draws=draws,
        rounding='Python round: translation6 decimals(m), yaw4 decimals(deg), light3 decimals; all effective values serialized')
    return rack, instrument, ryaw, iyaw, intensity, family, audit


def generate_definitions(directory):
    """Create the first candidate set once, with deterministic explicit deltas.

    Runtime outcomes and policy performance are never inputs. A later geometric
    correction requires a recorded definition revision rather than a new seed.
    """
    import yaml
    config = yaml.safe_load(STANDARD_CONFIG.read_text())
    lock = json.loads((ROOT / 'config/lab_cuvette_loading/Project_v1/assets.lock.json').read_text())
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'scenes').mkdir()
    candidates = [candidate_parameters(index) for index in range(11)]
    identities = []
    for index, (rack_delta, instrument_delta, rack_yaw, instrument_yaw, intensity, family, generation) in enumerate(candidates):
        scene_id = SCENE_IDS[index]
        rack = dict(origin_m=[a+b for a, b in zip(config['rack']['origin_m'], [*rack_delta, 0.])],
                    yaw_deg=config['rack']['yaw_deg']+rack_yaw)
        instrument = dict(origin_m=[a+b for a, b in zip(config['scene']['instrument_xyz_m'], [*instrument_delta, 0.])],
                          yaw_deg=config['scene']['instrument_yaw_deg']+instrument_yaw)
        params = dict(rack=rack, instrument=instrument,
            vessel_initial_yaw_deg=config['vessel']['yaw_deg']+rack_yaw,
            target_vessel_yaw_deg=config['vessel']['yaw_deg']+instrument_yaw,
            retreat_lateral_m=_rotate_xy(config['control']['retreat_lateral_m'], instrument_yaw),
            lighting=dict(prim_path='/World/Light', type='DomeLight', intensity=intensity,
                          intensity_units='USD light intensity; baseline authoring value1000', exposure=0.))
        definition = dict(scene_id=scene_id, suite_version=SUITE_VERSION,
            source_configuration=STANDARD_CONFIG.relative_to(ROOT).as_posix(),
            source_configuration_sha256=hashlib.sha256(STANDARD_CONFIG.read_bytes()).hexdigest(),
            source_commit=BASELINE_COMMIT, source_seed=generation['seed'],
            candidate_revision='seeded_generation_r2', generation=generation,
            generation_method='one-time seeded stratified sampling; effective parameters frozen; no runtime RNG',
            change_family=family,
            declared_delta=dict(rack_translation_m=[*rack_delta, 0.],
                instrument_translation_m=[*instrument_delta, 0.], rack_yaw_deg=rack_yaw,
                instrument_yaw_deg=instrument_yaw, dome_intensity_scale=intensity/1000.),
            actual_parameters=params,
            allowed_uses=['demonstration', 'training', 'policy_evaluation'] if index == 0 else ['policy_evaluation'],
            fixed_source_slot_id=config['rack']['selected_slot_id'],
            fixed_target_seat_id=config['adapter']['selected_target_seat_id'],
            initial_robot=copy.deepcopy(config['robot']),
            cameras=copy.deepcopy(config['cameras']),
            asset_revision=dict(repository=lock['repository'], revision=lock['revision'], asset_id=config['asset_id']),
            initialization_rules=dict(reset_repetitions=3, settle_seconds=4.,
                configured_pose_position_tolerance_m=1.e-6, configured_pose_rotation_tolerance_deg=1.e-5,
                settled_vessel_position_repeatability_m=.0002, settled_vessel_orientation_repeatability_deg=1.,
                no_initial_illegal_overlap=True, source_slot_unchanged=True, target_seat_unchanged=True,
                all_components_and_collisions_follow_assembly=True, side_camera_continuous=True,
                robot_initial_joints_fixed=True, camera_pixels_need_not_be_identical=True),
            unchanged=dict(geometry=True, mass=True, contact_parameters=True, physics=True,
                robot_base=True, robot_initial_joints=True, camera_calibration=True,
                public_observation=True, action_interface=True, scoring_thresholds=True))
        from demos.lab_cuvette_size_v1.scene import layout
        # Existing layout needs mapping-style get in addition to attributes;
        # OmegaConf supplies the same semantics used by the production task.
        from omegaconf import OmegaConf
        working = OmegaConf.create(_apply_values(config, definition))
        values = layout(working)
        definition['frames'] = dict(convention='column vectors: world=Rz@local+origin; metres, degrees',
            source_floor_world_m=values['source_floor'].tolist(),
            target_loading_floor_world_m=values['target_floor'].tolist(),
            original_seat_floor_world_m=values['seat_original_floor'].tolist(),
            source_cuvette_initial_bottom_world_m=(values['source_floor']+[0, 0, config['scene']['initial_bottom_gap_m']]).tolist(),
            blue_neighbor_initial= [{key: item.tolist() if hasattr(item, 'tolist') else item
                                    for key, item in row.items()} for row in values['neighbors']],
            rack_rotation_world=values['rack_rotation'].tolist(),
            instrument_rotation_world=values['instrument_rotation'].tolist(),
            target_loading_offset_local_m=list(config['geometry']['target_loading_offset_local_m']),
            insertion_axis_world=[0., 0., -1.], target_depth_m=values['target_depth_m'])
        definition['definition_sha256'] = canonical_sha(definition)
        path = directory / 'scenes' / (scene_id+'.json')
        path.write_text(json.dumps(definition, indent=2, ensure_ascii=False)+'\n')
        identities.append(dict(scene_id=scene_id, path='scenes/'+path.name,
                               definition_sha256=definition['definition_sha256']))
    suite = dict(schema=SUITE_VERSION, suite_version=SUITE_VERSION,
        standard_scene_id='standard', random10_scene_ids=list(SCENE_IDS[1:]), scenes=identities,
        source_commit=BASELINE_COMMIT, source_configuration=STANDARD_CONFIG.relative_to(ROOT).as_posix(),
        candidate_revision='seeded_generation_r2',
        generation_method='one-time numpy PCG64 seeded stratified sampling; no runtime sampling',
        design_ranges=dict(rack_translation_max_abs_m=.006, instrument_translation_max_abs_m=.006,
            assembly_yaw_max_abs_deg=1., dome_intensity_min=900., dome_intensity_max=1100.),
        selection_basis='Small assembly perturbations around demonstrated workspace; geometric and complete Teacher validation required; no GPT/VLA selection',
        validation_status='Candidate definitions; run receipts are stored separately under ignored outputs')
    (directory/'suite.json').write_text(json.dumps(suite, indent=2)+'\n')
    return suite


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate-directory', type=Path)
    parser.add_argument('--scene', default='standard')
    args = parser.parse_args()
    result = generate_definitions(args.generate_directory) if args.generate_directory else load_scene_definition(args.scene)
    print(json.dumps(result, indent=2, ensure_ascii=False))
