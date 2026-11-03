"""Resolve versioned geometry, physical gates and diagnostic scales separately."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path

import numpy as np

from .geometry import yaw_rotation

ROOT = Path(__file__).resolve().parents[2]
PARAMETERS = ROOT/'config/lab_cuvette_loading/Progress_v1/progress.json'
SCHEMA_VERSION = 'labsim.Progress_v1.v1'
EVALUATOR_VERSION = 'Progress_v1.causal_physics.v1'


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def get(value, path, default=None):
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _merge(destination, values):
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _merge(destination[key], value)
        else:
            destination[key] = copy.deepcopy(value)


class _Attr(dict):
    __getattr__ = dict.__getitem__


def _attrs(value):
    return _Attr({k: _attrs(v) for k, v in value.items()}) if isinstance(value, dict) else value


def resolve_config(task_cfg_dict, episode_metadata=None, initial_sample=None, overrides=None):
    """Return a JSON-safe immutable-input configuration with a content hash.

    ``initial_sample`` is accepted for API parity; no adaptive thresholds or
    future trajectory statistics are fitted. Metadata ``layout`` and
    ``vessel_body_local_bounds_m`` may bind actual runtime measurements.
    """
    try:
        from omegaconf import OmegaConf
        cfg = OmegaConf.to_container(task_cfg_dict, resolve=True) if OmegaConf.is_config(task_cfg_dict) else plain(task_cfg_dict)
    except ImportError:
        cfg = plain(task_cfg_dict)
    if cfg.get('progress_schema_version') == SCHEMA_VERSION and 'geometry' in cfg and 'thresholds' in cfg:
        result = copy.deepcopy(cfg)
        if overrides:
            _merge(result, plain(overrides))
        result.pop('config_hash', None)
        result['config_hash'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return result
    metadata = plain(episode_metadata or {})
    defaults = json.loads(PARAMETERS.read_text())
    layout = metadata.get('layout', metadata.get('fixtures', {}))
    layout_source = 'episode_metadata.layout (actual scene)'
    if not layout:
        module = get(cfg, 'env.scene_layout_module', 'demos.lab_cuvette_size_v1.scene')
        try:
            layout = plain(importlib.import_module(module).layout(_attrs(cfg)))
            layout_source = module+'.layout(task_cfg)'
        except (KeyError, AttributeError, TypeError, ValueError):
            layout = {}
            layout_source = 'unavailable: task layout could not be resolved'
    sources = {}
    geometry = {}
    def geom(key, value, source):
        geometry[key] = plain(value)
        sources['geometry.'+key] = source
    for key, source_key in [('source_floor_world_m', 'source_floor'), ('source_rim_world_z_m', 'source_rim_z'),
                            ('source_rotation_world', 'rack_rotation'), ('source_inner_m', 'source_inner_m'),
                            ('target_loading_floor_world_m', 'target_floor'), ('target_original_seat_floor_world_m', 'seat_original_floor'),
                            ('target_rotation_world', 'instrument_rotation'), ('target_inner_m', 'target_inner_m')]:
        geom(key, layout.get(source_key), layout_source+'.'+source_key)
    geom('target_loading_offset_local_m', get(cfg, 'geometry.target_loading_offset_local_m', layout.get('target_loading_offset_local_m')), 'task.geometry.target_loading_offset_local_m; original seat remains fixed')
    geom('target_depth_m', get(cfg, 'geometry.target_depth_m', layout.get('target_depth_m')), 'task.geometry.target_depth_m')
    geom('preinsert_above_rim_m', get(cfg, 'control.preinsert_bottom_above_rim_m', .002), 'task.control.preinsert_bottom_above_rim_m; fixed diagnostic reference')
    geom('tcp_local_translation_m', get(cfg, 'robot.tcp_local_m'), 'task.robot.tcp_local_m; panda_hand to right_gripper')
    geom('tcp_local_quaternion_wxyz', get(cfg, 'robot.tcp_quaternion_wxyz'), 'task.robot.tcp_quaternion_wxyz; validated by capture Lula FK')
    bounds = metadata.get('vessel_body_local_bounds_m')
    bound_source = 'episode_metadata.vessel_body_local_bounds_m (actual transformed visual points)'
    asset_id = get(cfg, 'vessel.asset_id', cfg.get('asset_id'))
    registry_relative = 'assets/lab_cuvette_loading/Size_v1/registry.json'
    registry_candidates = [ROOT/get(cfg, 'asset_registry', registry_relative)]
    asset_root = os.environ.get('LABSIM_ASSET_ROOT')
    if asset_root:
        registry_candidates.extend([Path(asset_root)/registry_relative, Path(asset_root)/'lab_cuvette_loading/Size_v1/registry.json'])
    registry_candidates.append(ROOT/registry_relative)
    if bounds is None:
        expected_sha = get(cfg, 'asset_selection.asset_sha256')
        for registry_path in dict.fromkeys(registry_candidates):
            try:
                registry = json.loads(registry_path.read_text())
            except (OSError, ValueError):
                continue
            entry = registry.get('assets', {}).get(asset_id, {})
            if expected_sha and entry.get('asset_sha256') != expected_sha:
                continue
            bounds = entry.get('actual_body_bounds_m')
            if bounds is not None:
                bound_source = str(registry_path)+': assets.'+str(asset_id)+'.actual_body_bounds_m; registered asset SHA matches episode binding' if expected_sha else str(registry_path)+': assets.'+str(asset_id)+'.actual_body_bounds_m; current registered asset metadata'
                break
    geom('vessel_body_local_bounds_m', bounds, bound_source if bounds is not None else 'unavailable: no verified body-local bounds')
    bottom_ref = top_ref = None
    if bounds is not None:
        b = np.asarray(bounds, float)
        bottom_ref = np.r_[(b[0, :2]+b[1, :2])/2, b[0, 2]]
        top_ref = np.r_[(b[0, :2]+b[1, :2])/2, b[1, 2]]
    geom('vessel_bottom_reference_body_m', bottom_ref, bound_source+'; bottom-plane XY centre, not USD-root assumption')
    geom('vessel_top_reference_body_m', top_ref, bound_source+'; top-plane XY centre')
    height = get(cfg, 'robot.grasp_above_bottom_m')
    geom('grasp_reference_body_m', [0., 0., float(height)] if height is not None else None, 'task.robot.grasp_above_bottom_m; configured legal grip reference, not measured pressure centre')
    geom('legal_grasp_band_body_z_m', [float(height)-.005, float(height)+.005] if height is not None else None, 'Progress_v1 new definition: +/-5mm around configured grip height')
    yaw = get(cfg, 'robot.gripper_yaw_deg')
    geom('grasp_tcp_rotation_world', yaw_rotation(math.radians(yaw)) @ np.diag([1., -1., -1.]) if yaw is not None else None, 'task.robot.gripper_yaw_deg; documented static Rz(yaw)Rx(pi), not teacher phase')
    geom('allowed_yaw_symmetry_order', 1, 'Progress_v1 conservative physical frame; square appearance does not imply equivalent seat orientations')
    geom('gripper_clearance_scope', 'actual panda_hand and two finger link input-vertex AABB separation lower bound; cooked geometry unverified', 'PhysicsRecorder.hand_clearance; TCP distance is auxiliary only')
    thresholds = copy.deepcopy(defaults['thresholds'])
    for key in thresholds:
        sources['thresholds.'+key] = ('original independent scorer literal' if key in {'bilateral_force_N', 'bilateral_hold_s', 'grasp_loss_hold_s', 'source_clearance_m', 'lift_started_m', 'held_transport_displacement_m', 'release_hold_s'} else 'Progress_v1 new diagnostic definition')
    mappings = {
        'grasp_translation_m': ('gripper.max_relative_position_drift_m', .0002),
        'grasp_rotation_rad': ('gripper.max_relative_orientation_drift_deg', 1.),
        'alignment_lateral_m': ('control.alignment_budget_m', .000015),
        'alignment_tilt_rad': ('control.tilt_budget_deg', .02),
        'alignment_yaw_rad': ('control.yaw_budget_deg', .1),
        'support_min_N': ('demo_release.min_support_N', .1),
        'support_gap_m': ('demo_release.bottom_distance_m', .00005),
        'overlap_m': ('acceptance.steady_source_penetration_m', .00005),
        'retreat_clearance_m': ('acceptance.actual_retreat_clearance_m', .04),
        'stable_duration_s': ('demo_release.observe_s', 3.),
        'stable_position_drift_m': ('demo_release.position_drift_m', .0002),
        'stable_orientation_change_rad': ('demo_release.orientation_change_deg', 1.),
        'upright_after_release_rad': ('acceptance.upright_after_release_deg', 1.)}
    mappings.update({
        'stall_window_s': ('control.jam_detection.window_s', .3),
        'stall_command_down_min_m': ('control.jam_detection.command_down_min_m', .00015),
        'stall_actual_down_max_m': ('control.jam_detection.vessel_down_max_m', .000025)})
    for key, (path, fallback) in mappings.items():
        value = get(cfg, path, fallback)
        thresholds[key] = math.radians(float(value)) if key.endswith('_rad') else float(value)
        sources['thresholds.'+key] = 'independent scorer reads task.'+path+(' (default)' if get(cfg, path) is None else '')
    width = float(get(cfg, 'vessel.outer_xy_m', [.0125])[0])
    thresholds['finger_open_min_m'] = float(get(cfg, 'scorer.finger_joint_open_min_m', width/2+.001))
    sources['thresholds.finger_open_min_m'] = 'independent scorer: task.scorer.finger_joint_open_min_m or nominal vessel X/2 +1mm'
    hz = float(get(cfg, 'physics.hz', get(cfg, 'env.physics_hz', 240)))
    thresholds['maximum_evidence_gap_s'] = float(metadata.get('sample_interval_s', 1/hz))*thresholds['sample_gap_tolerance_factor']
    sources['thresholds.maximum_evidence_gap_s'] = 'input evidence cadence (metadata.sample_interval_s or physics.hz) times declared gap tolerance'
    result = dict(progress_schema_version=SCHEMA_VERSION, progress_evaluator_version=EVALUATOR_VERSION,
                  parameters_version=defaults['version'], task='lab_cuvette_loading',
                  scene_version=get(cfg, 'project.scene_version', cfg.get('version')),
                  asset_id=asset_id, asset_selection=plain(cfg.get('asset_selection', {})),
                  geometry=geometry, thresholds=thresholds, normalization=defaults['normalization'], sources=sources,
                  criterion_scope='Alignment gates are the existing scorer loaded-pose-candidate checks that read control budgets. They are not a new final accuracy claim. Original final scorer remains authoritative.',
                  reward_adapter=dict(enabled=False, original_reward_unchanged=True))
    source_floor = geometry.get('source_floor_world_m')
    source_rim = geometry.get('source_rim_world_z_m')
    result['normalization']['extraction_depth_scale_m'] = float(source_rim-source_floor[2]) if source_floor is not None and source_rim is not None else None
    for key in result['normalization']:
        sources['normalization.'+key] = 'Progress_v1 fixed diagnostic scale; not acceptance threshold'
    sources['normalization.extraction_depth_scale_m'] = 'source rim world Z minus source floor world Z; diagnostic travel normalization'
    if overrides:
        for key in overrides:
            if key not in {'geometry', 'thresholds', 'normalization'}:
                raise ValueError('Progress configuration override must target geometry, thresholds or normalization: '+key)
        _merge(result, plain(overrides))
        for group, values in overrides.items():
            for key in values:
                sources[group+'.'+key] = 'explicit Progress configuration override'
    result = plain(result)
    result['config_hash'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result
