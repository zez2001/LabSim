"""Authored assembly checks and recorded reset consistency for the scene suite.

Comparison helpers are CPU-only. Isaac/USD imports remain inside the runtime
functions, which receive an already-running SimulationApp from the launcher.
No function moves a dynamic object or changes a physical task threshold.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import time

import numpy as np

from demos.lab_cuvette_project_release_v1.scene_suite import _plain


class SceneInitializationError(RuntimeError):
    """Declared scene and authored runtime scene differ."""


class ReferenceControlError(RuntimeError):
    """The static reference hold could not execute its requested control tick."""


def _safe(value):
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _safe(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    return value


def _write(path, value):
    Path(path).write_text(json.dumps(_safe(value), ensure_ascii=False,
        indent=2, allow_nan=False)+'\n', encoding='utf-8')


def quaternion_angle_deg(first, second):
    try:
        a, b = np.asarray(first, float), np.asarray(second, float)
    except (TypeError, ValueError):
        return None
    if a.shape != (4,) or b.shape != (4,) or not np.isfinite([*a, *b]).all():
        return None
    lengths = np.linalg.norm(a), np.linalg.norm(b)
    if min(lengths) <= 1e-12:
        return None
    cosine = float(np.clip(abs(np.dot(a/lengths[0], b/lengths[1])), 0., 1.))
    return math.degrees(2*math.acos(cosine))


def compare_pose(expected, actual, *, position_tolerance_m=1.e-6,
                 orientation_tolerance_deg=1.e-5):
    """Compare declared fields only; missing or nonfinite values fail closed."""
    errors = []
    distance, angle = None, None
    if 'position_m' in expected:
        a, b = np.asarray(expected['position_m'], float), np.asarray(actual.get('position_m', []), float)
        if a.shape != (3,) or b.shape != (3,) or not np.isfinite([*a, *b]).all():
            errors.append('position_missing_or_nonfinite')
        else:
            distance = float(np.linalg.norm(a-b))
            if distance > position_tolerance_m:
                errors.append('position_mismatch')
    if 'quaternion_wxyz' in expected:
        angle = quaternion_angle_deg(expected['quaternion_wxyz'], actual.get('quaternion_wxyz', []))
        if angle is None:
            errors.append('orientation_missing_or_nonfinite')
        elif angle > orientation_tolerance_deg:
            errors.append('orientation_mismatch')
    return dict(passed=not errors, errors=errors, position_error_m=distance,
        orientation_error_deg=angle, position_tolerance_m=position_tolerance_m,
        orientation_tolerance_deg=orientation_tolerance_deg)


def window_consistency(rows, *, position_tolerance_m=.0002, orientation_tolerance_deg=1.):
    if not rows:
        return dict(passed=False, reason='empty_window', samples=0)
    try:
        positions = np.asarray([row.get('object_position_m', []) for row in rows], float)
    except (TypeError, ValueError):
        return dict(passed=False, reason='invalid_position', samples=len(rows))
    quaternions = [row.get('object_quaternion_wxyz', row.get('quaternion_wxyz', [])) for row in rows]
    if positions.shape != (len(rows), 3) or not np.isfinite(positions).all():
        return dict(passed=False, reason='invalid_position', samples=len(rows))
    angles = [quaternion_angle_deg(quaternions[0], value) for value in quaternions]
    if any(angle is None for angle in angles):
        return dict(passed=False, reason='invalid_orientation', samples=len(rows))
    drift = float(np.linalg.norm(positions-positions[0], axis=1).max())
    turn = max(angles)
    return dict(passed=drift <= position_tolerance_m and turn <= orientation_tolerance_deg,
        samples=len(rows), position_drift_m=drift, orientation_change_deg=turn,
        position_tolerance_m=position_tolerance_m, orientation_tolerance_deg=orientation_tolerance_deg)


def repeatability(records, *, position_tolerance_m=.0002, orientation_tolerance_deg=1.):
    rows = [row['settled'] for row in records if row.get('settled') is not None]
    answer = window_consistency(rows, position_tolerance_m=position_tolerance_m,
        orientation_tolerance_deg=orientation_tolerance_deg)
    answer['reset_count'] = len(records)
    answer['available_settled_count'] = len(rows)
    if len(rows) != len(records):
        answer.update(passed=False, reason='missing_settled_record')
    return answer


def _yaw_quaternion(degrees):
    angle = math.radians(float(degrees))/2
    return [math.cos(angle), 0., 0., math.sin(angle)]


def _usd_pose(stage, path):
    from pxr import UsdGeom
    from scipy.spatial.transform import Rotation
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid() or not prim.IsActive():
        return dict(available=False, path=path)
    row = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim), float)
    matrix = row.T.copy()
    scale = float(UsdGeom.GetStageMetersPerUnit(stage))
    matrix[:3, 3] *= scale
    rotation = matrix[:3, :3]
    # Root assemblies are rigid. Report scale separately rather than silently
    # treating a scaled basis as a calibrated rotation.
    basis_scale = np.linalg.norm(rotation, axis=0)
    normalized = rotation/basis_scale if np.all(basis_scale > 0) else np.eye(3)
    xyzw = Rotation.from_matrix(normalized).as_quat()
    return dict(available=True, path=path, position_m=matrix[:3, 3].tolist(),
        quaternion_wxyz=np.roll(xyzw, 1).tolist(), world_from_prim_column=matrix.tolist(),
        basis_scale=basis_scale.tolist(), source='UsdGeom.XformCache; actual composed authored USD')


def configure_context(task, ctx):
    """Validate the newly built stage before its first recorded gravity step.

    Called only by the release task hook. Legacy configurations are a no-op;
    standard suite selection reads the baseline light without authoring it.
    """
    cfg = _plain(getattr(task, 'cfg', getattr(task, 'base_cfg', {})))
    membership = cfg.get('scene_suite')
    if not membership:
        return None
    from pxr import Usd, UsdGeom, UsdPhysics, UsdLux
    stage = ctx['stage']
    scene_id = membership['scene_id']
    expected_light = membership['actual_parameters']['lighting']
    light = UsdLux.DomeLight.Get(stage, expected_light['prim_path'])
    if not light:
        _write(Path(task.episode_dir)/'authored_scene_validation.json', dict(
            schema='labsim.scene_suite.authored_scene_validation.v1', scene_id=scene_id,
            passed=False, errors=['configured_dome_light_missing'], expected_light=expected_light))
        raise SceneInitializationError('Expected configured DomeLight is missing')
    if scene_id != 'standard':
        light.GetIntensityAttr().Set(float(expected_light['intensity']))
        light.GetExposureAttr().Set(float(expected_light.get('exposure', 0.)))
    light_actual = dict(intensity=light.GetIntensityAttr().Get(), exposure=light.GetExposureAttr().Get(),
        prim_path=expected_light['prim_path'], changed_by_suite=scene_id != 'standard')
    fixtures = ctx['fixtures']
    expected = {
        'rack': dict(position_m=list(cfg['rack']['origin_m']), quaternion_wxyz=_yaw_quaternion(cfg['rack']['yaw_deg'])),
        'instrument': dict(position_m=list(cfg['scene']['instrument_xyz_m']), quaternion_wxyz=_yaw_quaternion(cfg['scene']['instrument_yaw_deg'])),
        'robot': dict(position_m=list(cfg['robot']['base_m'])),
        'cuvette': dict(position_m=np.asarray(fixtures['source_floor'])+[0, 0, cfg['scene']['initial_bottom_gap_m']],
                        quaternion_wxyz=_yaw_quaternion(cfg['vessel']['yaw_deg'])),
        'source_slot': dict(position_m=np.asarray(fixtures['source_floor'])),
        'target_seat': dict(position_m=np.asarray(fixtures['seat_original_floor'])-
                            np.asarray(fixtures['instrument_rotation'])@np.array([0., 0., .002])),
    }
    paths = dict(rack='/World/SourceRack', instrument='/World/Instrument', robot='/World/Franka',
        cuvette='/World/Cuvette', source_slot='/World/SourceRack/Slots/'+cfg['rack']['selected_slot_id'],
        target_seat='/World/Instrument/Frames/'+cfg['adapter']['selected_target_seat_id'])
    for index, neighbor in enumerate(fixtures['neighbors']):
        name = 'neighbor_'+str(index)
        paths[name] = neighbor['prim_path']
        expected[name] = dict(position_m=neighbor['position'],
            quaternion_wxyz=_yaw_quaternion(cfg['vessel']['yaw_deg']))
    actual = {name: _usd_pose(stage, path) for name, path in paths.items()}
    checks = {name: compare_pose(value, actual[name]) for name, value in expected.items()}
    configured_q = np.asarray(cfg['robot']['initial_joint_positions'], float)
    actual_q = np.asarray(ctx['robot'].get_joint_positions(), float)
    joints_valid = (configured_q.shape == actual_q.shape == (9,) and
        np.isfinite(actual_q).all() and
        float(np.max(np.abs(configured_q[:7]-actual_q[:7]))) <= 1.e-6 and
        float(np.max(np.abs(configured_q[7:]-actual_q[7:]))) <= 1.e-6)
    colliders, visual_geometry = [], []
    for prim in Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()):
        if prim.IsActive() and prim.HasAPI(UsdPhysics.CollisionAPI):
            colliders.append(str(prim.GetPath()))
        if prim.IsActive() and '/Visual' in str(prim.GetPath()) and (
                prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube)):
            visual_geometry.append(str(prim.GetPath()))
    counts = {key: sum(path.startswith(prefix+'/') for path in colliders)
        for key, prefix in [('rack', paths['rack']), ('instrument', paths['instrument']),
                            ('cuvette', paths['cuvette']), ('robot', paths['robot'])]}
    counts['neighbors'] = {name: sum(path.startswith(path_prefix+'/') for path in colliders)
        for name, path_prefix in paths.items() if name.startswith('neighbor_')}
    visual_counts = {key: sum(path.startswith(prefix+'/') for path in visual_geometry)
        for key, prefix in [('rack', paths['rack']), ('instrument', paths['instrument']), ('cuvette', paths['cuvette'])]}
    visual_counts['neighbors'] = {name: sum(path.startswith(path_prefix+'/') for path in visual_geometry)
        for name, path_prefix in paths.items() if name.startswith('neighbor_')}
    relative_yaw = math.radians(float(cfg['vessel']['yaw_deg'])-float(cfg['rack']['yaw_deg']))
    width, length = cfg['vessel'].get('actual_outer_dimensions_m', [*cfg['vessel']['outer_xy_m'], cfg['vessel']['height_m']])[:2]
    projected = [abs(math.cos(relative_yaw))*width+abs(math.sin(relative_yaw))*length,
                 abs(math.sin(relative_yaw))*width+abs(math.cos(relative_yaw))*length]
    source_margin = (float(cfg['rack']['inner_m'])-np.asarray(projected))/2
    component_checks = dict(rack_50_collision_shapes=counts['rack'] == 50,
        rack_50_visual_shapes=visual_counts['rack'] == 50,
        instrument_8_visual_meshes=visual_counts['instrument'] == 8,
        cuvette_visual_mesh_present=visual_counts['cuvette'] > 0,
        neighbor_visual_meshes_present=all(value > 0 for value in visual_counts['neighbors'].values()),
        instrument_8_original_collision_shapes=counts['instrument'] == 8,
        cuvette_28_collision_shapes=counts['cuvette'] == 28,
        robot_collision_shapes_present=counts['robot'] > 0,
        declared_robot_initial_joints=bool(joints_valid),
        neighbor_collision_shapes_present=all(value == 28 for value in counts['neighbors'].values()),
        no_second_instrument=not bool(stage.GetPrimAtPath('/World/NeighborInstrument')),
        no_engineering_adapter=not bool(stage.GetPrimAtPath('/World/Instrument/EngineeringAdapterA')),
        source_initial_clearance_nonnegative=bool(np.min(source_margin) >= 0.),
        source_initial_bottom_gap_nonnegative=float(cfg['scene']['initial_bottom_gap_m']) >= 0.,
        source_slot_exists=actual['source_slot']['available'], target_seat_exists=actual['target_seat']['available'],
        dome_intensity_matches=abs(float(light_actual['intensity'])-float(expected_light['intensity'])) <= 1.e-3,
        dome_exposure_matches=abs(float(light_actual['exposure'])-float(expected_light.get('exposure', 0.))) <= 1.e-6)
    receipt = dict(schema='labsim.scene_suite.authored_scene_validation.v1', scene_id=scene_id,
        runtime_kind=str(ctx.get('validation_runtime_kind', 'native_builder_context')),
        stage_meters_per_unit=float(UsdGeom.GetStageMetersPerUnit(stage)),
        timing='Offline composed USD only; no PhysicsRecorder or gravity steps' if
            ctx.get('validation_runtime_kind') == 'offline_usd_composition' else
            'After existing builder/reset; before PhysicsRecorder first gravity step',
        configured=expected, authored_actual=actual, comparisons=checks,
        lighting=dict(expected=expected_light, actual=light_actual),
        collision_shape_counts=counts, collision_paths=colliders, component_checks=component_checks,
        visual_geometry_counts=visual_counts, visual_geometry_paths=visual_geometry,
        robot_initial_joint_check=dict(configured=configured_q, actual=actual_q,
            passed=bool(joints_valid), arm_tolerance_rad=1.e-6, finger_tolerance_m=1.e-6,
            source=str(ctx.get('robot_joint_state_source', 'native articulation get_joint_positions')),
            native_articulation_verified=ctx.get('robot_joint_state_source') != 'configuration_mock',
            timing='Before first recorded gravity step'),
        source_initial_analytic_xy_margin_m=source_margin,
        configured_target_loading_floor_world_m=fixtures['target_floor'],
        configured_original_seat_floor_world_m=fixtures['seat_original_floor'],
        passed=all(item['passed'] for item in checks.values()) and all(component_checks.values()),
        limitations=['Composed USD/input collision registration; not cooked PhysX buffer readback or a full-arm path collision certificate.'])
    _write(Path(task.episode_dir)/'authored_scene_validation.json', receipt)
    if not receipt['passed']:
        raise SceneInitializationError('Configured scene differs from authored assembly; see authored_scene_validation.json')
    return receipt


def _state(task):
    debug = copy.deepcopy(task.get_debug_observation())
    keys = ('t', 'physics_step', 'object_position_m', 'object_quaternion_wxyz',
        'quaternion_wxyz', 'source_bottom_z_m', 'source_bottom_gap_m', 'source_rack_penetration_m',
        'tilt_deg', 'linear_velocity_native_m_s', 'angular_velocity_native_rad_s',
        'fd_com_velocity_m_s', 'fd_angular_velocity_rad_s', 'environment_net_force_N',
        'environment_sum_force_magnitudes_N', 'finger_contact_N',
        'forbidden_robot_environment_contact', 'actual_tcp_position_m', 'actual_tcp_quaternion_wxyz',
        'joints9', 'joint_velocities9')
    return _safe({key: debug.get(key) for key in keys})


def _finite_vector(value, length=3):
    try:
        vector = np.asarray(value, float)
        return vector.shape == (length,) and bool(np.isfinite(vector).all())
    except (TypeError, ValueError):
        return False


def closure_status(episode_dir, episode_id):
    """Read only committed completion identities and closed H5 metadata."""
    import h5py
    directory = Path(episode_dir)
    entries = []
    for marker in sorted(directory.rglob('*_complete.json')):
        payload = json.loads(marker.read_text())
        path = marker.parent/payload['h5']
        row = dict(marker=str(marker.relative_to(directory)), h5=str(path.relative_to(directory)),
            h5_exists=path.is_file(), episode_identity_matches=payload.get('episode_id') == episode_id)
        if path.is_file():
            with h5py.File(path, 'r') as source:
                row.update(complete=bool(source.attrs.get('complete', False)),
                    publication_state=str(source.attrs.get('publication_state', 'unknown')),
                    h5_identity_matches=str(source.attrs.get('episode_id')) == episode_id,
                    finalization_identity_matches=str(source.attrs.get('finalization_id')) == payload.get('finalization_id'))
        row['closed'] = bool(row.get('h5_exists') and row['episode_identity_matches'] and
            row.get('complete') and row.get('publication_state') == 'complete' and
            row.get('h5_identity_matches') and row.get('finalization_identity_matches'))
        entries.append(row)
    return dict(entries=entries, result_exists=(directory/'result.json').is_file(),
        closed=bool(entries) and all(row['closed'] for row in entries) and (directory/'result.json').is_file())


def validate_settled_state(rows, cfg):
    """Existing source support/stability gates, with velocity channels retained."""
    data = _plain(cfg)
    if not rows:
        return dict(passed=False, errors=['no_observations'])
    end = rows[-1]
    seconds = float(data['acceptance']['window_s'])
    window = [row for row in rows if row['t'] >= end['t']-seconds-1.e-8]
    stability = window_consistency(window,
        position_tolerance_m=float(data['acceptance']['position_drift_m']),
        orientation_tolerance_deg=float(data['acceptance']['orientation_change_deg']))
    force = end.get('environment_net_force_N')
    support = float(force[2]) if isinstance(force, list) and len(force) == 3 else None
    penetration = end.get('source_rack_penetration_m')
    gap = end.get('source_bottom_gap_m')
    tilt = end.get('tilt_deg')
    flags = dict(stable_window=stability['passed'],
        full_three_second_window=bool(window and window[-1]['t']-window[0]['t'] >= seconds-1.1/float(data['physics']['control_hz'])),
        supported=support is not None and math.isfinite(support) and support >= float(data['demo_release']['min_support_N']),
        source_penetration_valid=penetration is not None and math.isfinite(penetration) and penetration <= float(data['acceptance']['steady_source_penetration_m']),
        source_bottom_supported=gap is not None and math.isfinite(gap) and abs(gap) <= float(data['demo_release']['bottom_distance_m']),
        upright=tilt is not None and math.isfinite(tilt) and tilt <= float(data['demo_release']['max_tilt_deg']),
        native_velocities_finite=all(_finite_vector(row.get('linear_velocity_native_m_s')) and
            _finite_vector(row.get('angular_velocity_native_rad_s')) for row in rows),
        no_robot_environment_contact=not any(row.get('forbidden_robot_environment_contact') is True for row in rows))
    velocity_differences = {}
    for name, native, finite_difference, threshold in (
        ('linear', 'linear_velocity_native_m_s', 'fd_com_velocity_m_s', float(data['acceptance']['linear_speed_m_s'])),
        ('angular', 'angular_velocity_native_rad_s', 'fd_angular_velocity_rad_s', float(data['acceptance']['angular_speed_rad_s']))):
        differences = [float(np.linalg.norm(np.asarray(row[native])-np.asarray(row[finite_difference])))
            for row in rows if _finite_vector(row.get(native)) and _finite_vector(row.get(finite_difference))]
        velocity_differences[name] = dict(maximum_disagreement=max(differences) if differences else None,
            warning_threshold=threshold, warning=bool(differences and max(differences) > threshold),
            gating=False, units='m/s' if name == 'linear' else 'rad/s')
    return dict(passed=all(flags.values()), checks=flags, stability=stability,
        source_net_vertical_force_N=support, source_rack_penetration_m=penetration,
        source_bottom_gap_m=gap, tilt_deg=tilt,
        velocity_channel_differences=velocity_differences,
        scope='Source analytic rack envelope/table penetration and measured aggregate environment support; not a global cooked-mesh penetration proof',
        native_velocity_policy='Both native and finite-difference signals retained; nonfinite API values are reported separately')


def validate_resets(app, cfg, output, geometry_audit, count=3):
    """Three independently rebuilt, fully recorded gravity/hold diagnostics."""
    if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 10:
        raise ValueError('Reset validation count must be3..10')
    from omegaconf import OmegaConf
    from factories.task_factory import create_task
    from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment
    output = Path(output)/'reset_validation'
    output.mkdir(parents=True, exist_ok=False)
    config = OmegaConf.create(_plain(cfg))
    if not config.get('scene_suite'):
        from demos.lab_cuvette_project_release_v1.scene_suite import select_scene
        config = select_scene(config, 'standard', purpose='eval')
    config.release.record_mode = 'eval'
    scene_id = config.scene_suite.scene_id
    config.release.record_purpose = 'policy_evaluation' if scene_id != 'standard' else 'lifecycle_diagnostic'
    config.scene_execution = dict(suite_run_id='reset_validation', scene_repetition_index=0,
        suite_episode_index=0, diagnostic_role='reset_consistency')
    records, errors = [], []
    started = time.perf_counter()
    task = None
    try:
        task = create_task(config.task_type, config, app, output, geometry_audit=geometry_audit)
        facade = ProjectEnvironment(task)
        hz = int(config.physics.control_hz)
        for index in range(count):
            record = dict(reset_index=index, validation_kind='reset_consistency', task_attempt=False)
            records.append(record)
            try:
                facade.reset(0, dict(mode='standard', teacher=False, policy_id='scene_reset_validation',
                    demonstrator_id='StaticJointHold', scene_id=scene_id))
                record.update(episode_id=task.episode_id, episode_directory=str(task.episode_dir),
                    configured_cuvette_bottom_world_m=(np.asarray(task.ctx['fixtures']['source_floor'])+
                    [0, 0, float(config.scene.initial_bottom_gap_m)]).tolist(),
                    initial=_state(task), configured_robot_joints=list(config.robot.initial_joint_positions),
                    authored_validation=json.loads((task.episode_dir/'authored_scene_validation.json').read_text()))
                rows = [record['initial']]
                held = task.robot.get_joint_positions()[:7].copy()
                trace = task.episode_dir/'reset_control_observations.jsonl'
                with trace.open('x', encoding='utf-8') as stream:
                    stream.write(json.dumps(rows[-1], allow_nan=False)+'\n')
                    for tick in range(4*hz):
                        if not app.is_running() or task.ended:
                            raise RuntimeError('Reset hold ended before four seconds')
                        observation = facade.observe()
                        receipt = facade.execute(dict(action_id=f'reset:{index}:{tick}',
                            episode_id=observation['episode_id'], observation_id=observation['observation_id'],
                            type='joint_position', values=held.tolist(), frame='joint', duration_s=1./hz,
                            gripper_opening_m=.08, gripper_effort_limit_N=float(config.env.gripper_effort_max_N)))
                        if receipt.get('executed_control_ticks') != 1 or receipt.get('safety_stopped') is True:
                            raise ReferenceControlError('Reset joint hold rejected or safety-stopped: '+str(receipt.get('stop_reason')))
                        rows.append(_state(task))
                        stream.write(json.dumps(rows[-1], allow_nan=False)+'\n')
                        if not (_finite_vector(rows[-1]['linear_velocity_native_m_s']) and
                                _finite_vector(rows[-1]['angular_velocity_native_rad_s'])):
                            raise RuntimeError('Nonfinite native velocity during reset hold')
                record['settled'] = rows[-1]
                record['settled_assembly_poses'] = {name: _usd_pose(task.ctx['stage'], row['path'])
                    for name, row in record['authored_validation']['authored_actual'].items()}
                record['support_and_stability'] = validate_settled_state(rows, config)
                record['camera_checks'] = {}
                from PIL import Image
                for name, image in facade.observe()['images'].items():
                    pixels = np.asarray(image)
                    valid = pixels.dtype == np.uint8 and pixels.ndim == 3 and pixels.shape[2] == 3 and bool(np.any(pixels))
                    path = task.episode_dir/(name+'_settled.png')
                    if valid:
                        Image.fromarray(pixels).save(path)
                    record['camera_checks'][name] = dict(available=bool(valid), shape=list(pixels.shape),
                        dtype=str(pixels.dtype), path=path.name if valid else None)
                record['passed'] = bool(record['support_and_stability']['passed'] and
                    all(row['available'] for row in record['camera_checks'].values()) and
                    set(record['camera_checks']) == {'side_camera', 'wrist_camera'})
                record['classification'] = 'RESET_CHECK_SUCCESS' if record['passed'] else 'INITIALIZATION_FAILURE'
            except Exception as error:
                record.update(passed=False, classification='INITIALIZATION_FAILURE'
                    if isinstance(error, SceneInitializationError) or 'initial' not in record else
                    'REFERENCE_CONTROLLER_FAILURE' if isinstance(error, ReferenceControlError) else 'ENVIRONMENT_EXCEPTION',
                    error=dict(type=type(error).__name__, message=str(error)))
                errors.append(dict(reset_index=index, **record['error']))
            finally:
                if task is not None and not task.ended:
                    try:
                        facade.finish('SCENE_RESET_VALIDATION_ONLY', failure_type='PROCESS_INTERRUPTED')
                    except Exception as error:
                        record.update(passed=False, closure_error=dict(type=type(error).__name__, message=str(error)))
                        errors.append(dict(reset_index=index, operation='diagnostic_close', **record['closure_error']))
                if getattr(task, 'episode_dir', None):
                    try:
                        record['record_closure'] = closure_status(task.episode_dir, task.episode_id)
                    except Exception as error:
                        record.update(passed=False, record_closure=dict(closed=False,
                            error=dict(type=type(error).__name__, message=str(error))))
                _write(output/'reset_validation_running.json', dict(scene_id=scene_id, records=records, errors=errors))
    finally:
        if task is not None:
            try:
                task.close()
            except Exception as error:
                errors.append(dict(operation='environment_close', type=type(error).__name__, message=str(error)))
    repeated = repeatability(records)
    result = dict(schema='labsim.scene_suite.reset_validation.v1', scene_id=scene_id,
        count_requested=count, count_recorded=len(records), resets=records,
        repeatability=repeated, errors=errors, passed=len(records) == count and not errors and
        all(record.get('passed') is True and record.get('record_closure', {}).get('closed') is True for record in records) and repeated['passed'],
        wall_seconds=time.perf_counter()-started, formal_task_attempts=0,
        termination='SCENE_RESET_VALIDATION_ONLY / PROCESS_INTERRUPTED',
        indexing='Nested reset_validation episodes are excluded from formal root episode membership',
        early_fall_evidence='Existing physics_records logs begin at physics_step0 before first public observation',
        pixel_identity_required=False)
    _write(output/'reset_validation_summary.json', result)
    return result
