"""Resolve a registered Size_v1 asset without changing the original A seat.

This pre-Isaac helper uses only registered measured metadata plus source/asset
content hashes. It does not pretend to remeasure USD vertices without USD or to
replace the separate current geometry/cooking/runtime gates.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = 'assets/lab_cuvette_loading/Size_v1/registry.json'
ORIGINAL_ASSET_DIRECTORY = 'assets/lab_cuvette_loading/V0_demo04'
CONTROL_ID = 'cuvette_xy_1250'
SOURCE_SHA = '8d52757227303edd4f38918ee04763481f08846fdd8daa6803295c8fc77c689d'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve_file(value):
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError('Registered asset dependency must be a repository file: ' + str(path))
    return path


def _finite_vector(value, length, field):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError('Invalid registered ' + field)
    values = [float(x) for x in value]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Nonfinite registered ' + field)
    return values


def _near(actual, expected, field, *, absolute=1e-8, relative=1e-6):
    actual, expected = float(actual), float(expected)
    if not math.isfinite(actual) or not math.isclose(actual, expected, abs_tol=absolute, rel_tol=relative):
        raise ValueError('Registered ' + field + ' does not match the preserved derivation rule')


def _check_record(record, control):
    if record.get('version') != 'Size_v1' or record.get('schema') != 'labsim.Size_v1.asset.v1':
        raise ValueError('Expected independent Size_v1 registered asset metadata')
    path = _resolve_file(record['asset_path'])
    if _sha(path) != record.get('asset_sha256'):
        raise ValueError('Registered asset SHA256 differs: ' + str(path))
    source = _resolve_file(record['source']['path'])
    if record['source'].get('sha256') != SOURCE_SHA or _sha(source) != SOURCE_SHA:
        raise ValueError('Preserved12.5mm source SHA256 differs')
    metadata_path = path.with_suffix('.json')
    if not metadata_path.is_file() or json.loads(metadata_path.read_text()) != record:
        raise ValueError('Registry entry and independent asset metadata disagree')
    if record.get('meters_per_unit') != 1 or record.get('up_axis') != 'Z' or record.get('default_prim') != '/Asset':
        raise ValueError('Asset must retain explicit metre/Z-up/defaultPrimAsset convention')
    checks = record.get('checks', {})
    if not checks or not all(value is True for value in checks.values()):
        raise ValueError('Registered asset reload/affine invariants are not all verified')
    nominal = _finite_vector(record['nominal_outer_xy_mm'], 2, 'nominalXY')
    scale = _finite_vector(record['axis_scale'], 3, 'axis_scale')
    dimensions = _finite_vector(record['actual_outer_dimensions_mm'], 3, 'actual_dimensions')
    if nominal[0] <= 0 or nominal[0] != nominal[1]:
        raise ValueError('Size_v1 changesX/Y by the same positive scale')
    _near(scale[0], nominal[0] / 12.5, 'Xscale', absolute=1e-12)
    _near(scale[1], scale[0], 'Yscale', absolute=1e-12)
    _near(scale[2], 1, 'Zscale', absolute=1e-12)
    _near(record['height_nominal_mm'], 67.5, 'nominal_height_mm', absolute=1e-12)
    original = _finite_vector(control['actual_outer_dimensions_mm'], 3, 'control_actual_dimensions')
    for axis in range(3):
        _near(dimensions[axis], original[axis] * scale[axis], 'actual_dimensions_mm',
              absolute=1e-4, relative=2e-6)
    bounds = record['actual_body_bounds_m']
    lo, hi = _finite_vector(bounds[0], 3, 'bounds_min'), _finite_vector(bounds[1], 3, 'bounds_max')
    _near(lo[2], 0, 'bottom_origin_m', absolute=1e-12)
    for axis in range(3):
        _near((hi[axis] - lo[axis]) * 1000, dimensions[axis], 'bounds_dimensions_mm', absolute=1e-8)
    _near(record['mass_kg'], .020, 'mass_kg')
    material = record['mass_properties']
    _near(material['mass_kg'], .020, 'integrated_mass_kg')
    _near(record['reloaded_mass_properties']['mass_kg'], .020, 'reloaded_mass_kg')
    com = _finite_vector(material['com_body_m'], 3, 'COM')
    if any(not lo[i] <= com[i] <= hi[i] for i in range(3)):
        raise ValueError('Registered COM is outside actual material envelope')
    principal = _finite_vector(material['principal_inertia_kg_m2'], 3, 'principal_inertia')
    if any(x <= 0 for x in principal):
        raise ValueError('Registered principal inertia must be positive')
    tensor = [_finite_vector(row, 3, 'full_inertia_tensor') for row in material['inertia_body_kg_m2']]
    if len(tensor) != 3:
        raise ValueError('Full inertia tensor must be3x3')
    for i in range(3):
        for j in range(3):
            _near(tensor[i][j], tensor[j][i], 'inertia_symmetry', absolute=1e-15)
    volume = float(material['material_volume_m3'])
    if volume <= 0 or not math.isfinite(volume):
        raise ValueError('Material volume must be positive')
    _near(volume, control['mass_properties']['material_volume_m3'] * scale[0] * scale[1],
          'XY_scaled_material_volume', absolute=1e-13, relative=3e-6)
    _near(material['homogeneous_density_kg_m3'], .020 / volume, 'fixed_mass_numerical_density', absolute=1e-6)
    if not record.get('mass_source') or not record.get('mass_distribution_assumption'):
        raise ValueError('Mass assumption and distribution basis are required')
    cavity = record.get('inner_cavity_sections', [])
    if len(cavity) != len(control.get('inner_cavity_sections', [])) or not cavity:
        raise ValueError('Missing registered cavity measurements')
    for actual, original_section in zip(cavity, control['inner_cavity_sections']):
        _near(actual['height_above_bottom_mm'], original_section['height_above_bottom_mm'], 'cavity_sectionZ_mm')
        for axis in 'XY':
            key = 'actual_central_inner_clear_width_' + axis + '_mm'
            _near(actual[key], original_section[key] * scale[0], key, absolute=1e-4, relative=2e-6)
    if record.get('material_attributes') != control.get('material_attributes'):
        raise ValueError('Size variants must inherit all registered material/contact attributes')
    colliders, base_colliders = record.get('collision_input_shapes', []), control.get('collision_input_shapes', [])
    if len(colliders) != 28 or len(base_colliders) != 28:
        raise ValueError('Size variants must retain all28 original thick-wall collision inputs')
    base = {c['prim']: c for c in base_colliders}
    for collider in colliders:
        if collider['prim'] not in base:
            raise ValueError('Unexpected or omitted collision input shape')
        reference = base[collider['prim']]
        for key in ('approximation', 'collision_enabled', 'contact_offset_m', 'rest_offset_m',
                    'configuration_attributes_excluding_vertex_arrays'):
            if collider.get(key) != reference.get(key):
                raise ValueError('Variant changed collision/contact configuration: ' + key)
    root_parameters = record.get('root_rigid_body_attributes', {})
    allowed_mass_fields = {'physics:centerOfMass', 'physics:diagonalInertia', 'physics:principalAxes'}
    for key, value in control.get('root_rigid_body_attributes', {}).items():
        if key not in allowed_mass_fields and root_parameters.get(key) != value:
            raise ValueError('Variant changed rigid-body parameter: ' + key)
    return path


def resolve_asset_config(cfg, asset_id=None):
    """Return a fresh matching-type config selecting a verified registered USD.

    Explicit argument wins, then the top-levelasset_id, then vessel.asset_id.
    Physics, rack/instrument directory and current target offset are preserved.
    The same operation is idempotent; reset can resolve the sameID again.
    """
    is_omega = False
    try:
        from omegaconf import OmegaConf
        is_omega = OmegaConf.is_config(cfg)
        value = OmegaConf.to_container(cfg, resolve=True) if is_omega else copy.deepcopy(cfg)
    except ImportError:
        value = copy.deepcopy(cfg)
    if not isinstance(value, dict):
        raise TypeError('Expected dict or OmegaConf configuration')
    ident = asset_id or value.get('asset_id') or value.get('vessel', {}).get('asset_id')
    if not isinstance(ident, str) or not ident:
        raise ValueError('Select a registered Size_v1 asset_id')
    directory = value.get('asset_directory', ORIGINAL_ASSET_DIRECTORY)
    if Path(directory).as_posix() != ORIGINAL_ASSET_DIRECTORY:
        raise ValueError('Size_v1 must keep the original V0_demo04 rack/instrument asset_directory')
    registry_path = _resolve_file(value.get('asset_registry', REGISTRY))
    registry = json.loads(registry_path.read_text())
    if registry.get('schema') != 'labsim.Size_v1.asset_registry.v1':
        raise ValueError('Unsupported Size_v1 asset registry')
    entries = registry.get('assets', {})
    if ident not in entries or CONTROL_ID not in entries:
        raise ValueError('Unknown registered Size_v1 asset_id: ' + ident)
    record, control = entries[ident], entries[CONTROL_ID]
    _check_record(control, control)
    path = _check_record(record, control)
    relative_path = path.relative_to(ROOT.resolve()).as_posix()
    source = value.setdefault('source', {})
    source['vessel'] = relative_path
    source['vessel_collision'] = relative_path
    value['asset_id'] = ident
    value['asset_registry'] = registry_path.relative_to(ROOT.resolve()).as_posix()
    value['asset_directory'] = directory
    value['derived_directory'] = path.parent.relative_to(ROOT.resolve()).as_posix()
    value['collision_scheme'] = path.stem
    vessel = value.setdefault('vessel', {})
    vessel.update(asset_id=ident,
        outer_xy_m=[x / 1000 for x in record['nominal_outer_xy_mm']],
        height_m=record['height_nominal_mm'] / 1000, mass_kg=record['mass_kg'],
        actual_outer_dimensions_m=[x / 1000 for x in record['actual_outer_dimensions_mm']],
        center_of_mass_m=copy.deepcopy(record['mass_properties']['com_body_m']),
        inertia_body_kg_m2=copy.deepcopy(record['mass_properties']['inertia_body_kg_m2']),
        axis_scale_from_control=copy.deepcopy(record['axis_scale']),
        # The inherited shared builder's source_mesh is the original14.85mm
        # CAD. Keep its legacy scale consistent; current USDs already contain
        # their one-time affine transform and must not be scaled a second time.
        xy_scale=record['nominal_outer_xy_mm'][0] / 14.85,
        xy_scale_basis='legacy original14.85mm CAD helper only; loaded USD already transformed',
        dimension_source='XY size hypothesis derived from preserved12.5mm control; not measured',
        mass_source=record['mass_source'])
    value['asset_selection'] = {'schema': 'labsim.Size_v1.asset_selection.v1',
        'asset_id': ident, 'asset_sha256': record['asset_sha256'],
        'source_path': record['source']['path'], 'source_sha256': record['source']['sha256'],
        'registry_path': value['asset_registry'], 'registry_sha256': _sha(registry_path),
        'validation_scope': 'Source/USD content hashes and independent registered measured dimensions/mass/contact metadata; separate geometry/cooking/runtime checks still required',
        'original_rack_and_instrument_preserved': True,
        'target_offset_automatically_adjusted': False,
        'mass_distribution_assumption': record['mass_distribution_assumption']}
    if is_omega:
        return OmegaConf.create(value)
    return value
