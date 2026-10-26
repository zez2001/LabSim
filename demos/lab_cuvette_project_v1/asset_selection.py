"""Atomically select one registered XY hypothesis; never edit the original seat."""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path(root, value):
    value = Path(str(value))
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Registry asset paths must stay relative to the declared asset root')
    resolved = (Path(root) / value).resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError('Registered asset path escapes declared root')
    return resolved


def select_registered_asset(config, *, asset_root, repository_root, asset_id=None):
    """Pure-stdlib selection used before Isaac; all variants retain their own USD.

    The registry and sidecar must agree and their declared bytes are verified.
    Geometry/cooking/physical task success remain independent later checks.
    """
    value = copy.deepcopy(config)
    ident = asset_id or value.get('asset_id') or value.get('vessel', {}).get('asset_id') or 'cuvette_xy_1000'
    registry_path = Path(str(value['asset_registry']))
    if not registry_path.is_absolute():
        registry_path = Path(repository_root) / registry_path
    registry = json.loads(registry_path.read_text())
    if registry.get('schema') != 'labsim.Size_v1.asset_registry.v1':
        raise ValueError('Unsupported registered vessel family')
    if ident not in registry.get('assets', {}):
        raise ValueError('Unknown registered asset_id: ' + str(ident))
    record = registry['assets'][ident]
    if record.get('asset_id') != ident:
        raise ValueError('Registry key and registered asset_id disagree')
    asset = _path(asset_root, record['asset_path'])
    sidecar = asset.with_suffix('.json')
    if _sha(asset) != record['asset_sha256']:
        raise ValueError('Selected asset differs from registered SHA256: ' + ident)
    if json.loads(sidecar.read_text()) != record:
        raise ValueError('Selected asset sidecar differs from its registry entry: ' + ident)
    source = _path(asset_root, record['source']['path'])
    if _sha(source) != record['source']['sha256']:
        raise ValueError('Registered source asset SHA256 differs: ' + ident)
    mass = record['mass_properties']
    numeric = [*record['nominal_outer_xy_mm'], *record['actual_outer_dimensions_mm'],
        record['height_nominal_mm'], record['mass_kg'], *mass['com_body_m'],
        *(number for row in mass['inertia_body_kg_m2'] for number in row)]
    if not all(math.isfinite(float(number)) for number in numeric) or float(record['mass_kg']) <= 0:
        raise ValueError('Registered geometry and mass properties must be finite')
    if record['meters_per_unit'] != 1 or record['up_axis'] != 'Z' or record['default_prim'] != '/Asset':
        raise ValueError('Registered asset must retain metre/Z-up/defaultPrim conventions')
    shapes = record.get('collision_input_shapes', [])
    if len(shapes) != 28 or not record.get('material_attributes'):
        raise ValueError('Registered vessel must preserve all28 collision inputs and contact metadata')
    value.update(asset_id=ident, derived_directory=str(asset.parent), collision_scheme=asset.stem)
    value.setdefault('source', {}).update(vessel=str(asset), vessel_collision=str(asset))
    vessel = value.setdefault('vessel', {})
    vessel.update(asset_id=ident, outer_xy_m=[float(x) / 1000 for x in record['nominal_outer_xy_mm']],
        height_m=float(record['height_nominal_mm']) / 1000, mass_kg=float(record['mass_kg']),
        actual_outer_dimensions_m=[float(x) / 1000 for x in record['actual_outer_dimensions_mm']],
        center_of_mass_m=copy.deepcopy(mass['com_body_m']), inertia_body_kg_m2=copy.deepcopy(mass['inertia_body_kg_m2']),
        principal_inertia_kg_m2=copy.deepcopy(mass['principal_inertia_kg_m2']),
        principal_axes_quaternion_wxyz=copy.deepcopy(mass['principal_axes_quaternion_wxyz']),
        axis_scale_from_control=copy.deepcopy(record['axis_scale']),
        xy_scale=float(record['nominal_outer_xy_mm'][0]) / 14.85,
        xy_scale_basis='Legacy original14.85mm CAD helper only; selected USD already derived; no second scale applied',
        mass_source=record['mass_source'], mass_distribution_assumption=record['mass_distribution_assumption'],
        dimension_source='Registered XY size hypothesis; not a real measured cuvette dimension',
        inner_cavity_sections=copy.deepcopy(record['inner_cavity_sections']),
        registered_material_attributes=copy.deepcopy(record['material_attributes']),
        registered_collision_input_shapes=copy.deepcopy(shapes))
    value['asset_selection'] = dict(schema='labsim.Project_v1.atomic_asset_selection.v1',
        asset_id=ident, asset_sha256=record['asset_sha256'],
        source_path=record['source']['path'], source_sha256=record['source']['sha256'],
        registry_path=str(registry_path), registry_sha256=_sha(registry_path),
        original_rack_and_instrument_preserved=True, target_offset_automatically_adjusted=False,
        mass_distribution_assumption=record['mass_distribution_assumption'],
        validation_scope='Registered USD/source/sidecar hashes and atomic geometric/mass/contact metadata; independent geometry, cooked collision and physical execution still required')
    width = float(record['nominal_outer_xy_mm'][0])
    slot = value.get('rack', {}).get('selected_slot_id', 'A1')
    seat = value.get('adapter', {}).get('selected_target_seat_id', 'candidate_far_hinge')
    value.setdefault('task', {})['instruction'] = (
        f'Physically load the {width:g}mm XY size-hypothesis cuvette from fixed white rack slot {slot} '
        f'into unchanged original internal seat {seat}, transfer support, release, retreat and leave stable for3seconds.')
    return value
