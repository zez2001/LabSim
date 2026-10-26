"""Atomically switch declared assets; fixture bytes do not simulate geometry."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from demos.lab_cuvette_project_v1.asset_selection import select_registered_asset


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def family(tmp_path):
    source = tmp_path / 'assets/control.usda'
    source.parent.mkdir()
    source.write_bytes(b'preserved source fixture')
    records = {}
    for ident, width in [('cuvette_xy_1000', 10.), ('cuvette_xy_1030', 10.3)]:
        path = tmp_path / 'assets' / (ident + '.usda')
        path.write_bytes(('registered fixture:' + ident).encode())
        record = dict(asset_id=ident, asset_path=path.relative_to(tmp_path).as_posix(),
            asset_sha256=sha(path.read_bytes()), source=dict(path='assets/control.usda', sha256=sha(source.read_bytes())),
            meters_per_unit=1, up_axis='Z', default_prim='/Asset', nominal_outer_xy_mm=[width, width],
            actual_outer_dimensions_mm=[width + 1e-6, width + 1e-6, 67.5], height_nominal_mm=67.5,
            mass_kg=.02, axis_scale=[width / 12.5, width / 12.5, 1], mass_source='20g assumption',
            mass_distribution_assumption='uniform material, fixed total mass',
            inner_cavity_sections=[dict(height_above_bottom_mm=10., width_mm=width - 2)],
            material_attributes=[dict(prim='/Asset/Looks/Physics', attributes={'physics:staticFriction':'0.6'})],
            collision_input_shapes=[dict(prim='/Asset/Collision/shape_' + str(i)) for i in range(28)],
            mass_properties=dict(com_body_m=[width * 1e-8, 0., .029], inertia_body_kg_m2=[[width * 1e-6, 0., 0.], [0., width * 1e-6, 0.], [0., 0., width * 1e-7]],
                principal_inertia_kg_m2=[width * 1e-7, width * 1e-6, width * 1e-6], principal_axes_quaternion_wxyz=[1., 0., 0., 0.]))
        path.with_suffix('.json').write_text(json.dumps(record))
        records[ident] = record
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps(dict(schema='labsim.Size_v1.asset_registry.v1', assets=records)))
    config = dict(asset_id='cuvette_xy_1000', asset_registry=str(registry),
        source=dict(vessel='old_1000.usda', vessel_collision='old_1000.usda'), vessel=dict(yaw_deg=90.),
        geometry=dict(target_loading_offset_local_m=[.00065, .000001, 0.]),
        physics=dict(contact_offset_m=.00005, dynamic_friction=.5),
        adapter=dict(selected_target_seat_id='candidate_far_hinge'))
    return tmp_path, config, records


def select(family, config=None, ident=None):
    root, baseline, records = family
    return select_registered_asset(config or baseline, asset_root=root, repository_root=root, asset_id=ident)


def test_default_asset_retains_1000_geometry_and_mass_values(family):
    selected = select(family)
    record = family[2]['cuvette_xy_1000']
    assert selected['asset_id'] == selected['vessel']['asset_id'] == 'cuvette_xy_1000'
    assert selected['vessel']['outer_xy_m'] == [.01, .01]
    assert selected['vessel']['height_m'] == .0675 and selected['vessel']['mass_kg'] == .02
    assert selected['vessel']['center_of_mass_m'] == record['mass_properties']['com_body_m']
    assert selected['vessel']['inertia_body_kg_m2'] == record['mass_properties']['inertia_body_kg_m2']


def test_yaml_asset_id_alone_atomically_switches_all_asset_fields(family):
    baseline = copy.deepcopy(family[1])
    baseline['asset_id'] = 'cuvette_xy_1030'
    selected = select(family, baseline)
    record = family[2]['cuvette_xy_1030']
    assert selected['source']['vessel'].endswith('cuvette_xy_1030.usda')
    assert selected['source']['vessel_collision'] == selected['source']['vessel']
    assert selected['collision_scheme'] == 'cuvette_xy_1030'
    assert selected['vessel']['outer_xy_m'] == [.0103, .0103]
    assert selected['vessel']['center_of_mass_m'] == record['mass_properties']['com_body_m']
    assert selected['vessel']['registered_collision_input_shapes'] == record['collision_input_shapes']
    assert selected['asset_selection']['asset_sha256'] == record['asset_sha256']
    assert '10.3mm' in selected['task']['instruction']
    for key in ('geometry', 'physics', 'adapter'):
        assert selected[key] == family[1][key]
    assert family[1]['source']['vessel'] == 'old_1000.usda'


def test_explicit_argument_precedes_yaml_without_mutating_it(family):
    selected = select(family, ident='cuvette_xy_1030')
    assert selected['asset_id'] == 'cuvette_xy_1030'
    assert family[1]['asset_id'] == 'cuvette_xy_1000'


def test_unknown_asset_id_is_actionable(family):
    with pytest.raises(ValueError, match='Unknown registered asset_id'):
        select(family, ident='not_registered')


def test_changed_usd_or_sidecar_never_silently_enters_a_run(family):
    root = family[0]
    (root / 'assets/cuvette_xy_1030.usda').write_bytes(b'changed fixture')
    with pytest.raises(ValueError, match='SHA256'):
        select(family, ident='cuvette_xy_1030')
