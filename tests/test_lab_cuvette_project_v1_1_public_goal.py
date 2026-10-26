"""CPU language contract checks; no Isaac imports, object truth, or API calls."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from policy.backends.cubence_project_v1_1_tools import ProjectV11RobotTools, SYSTEM_PROMPT


ROOT=Path(__file__).resolve().parents[1]


def language_class():
    # Execute the actual base language method and new override, without loading
    # the Isaac-dependent parent modules or substituting their method bodies.
    parent_path=ROOT/'tasks/lab_cuvette_loading_env_v1.py'
    parent_tree=ast.parse(parent_path.read_text())
    parent=next(n for n in parent_tree.body if isinstance(n,ast.ClassDef))
    parent_method=next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name=='get_task_language')
    source=ROOT/'tasks/lab_cuvette_loading_project_v1_1.py'
    tree=ast.parse(source.read_text())
    child=next(n for n in tree.body if isinstance(n,ast.ClassDef))
    method=next(n for n in child.body if isinstance(n,ast.FunctionDef) and n.name=='get_task_language')
    assert {n.attr for n in ast.walk(method) if isinstance(n,ast.Attribute)
            and isinstance(n.value,ast.Name) and n.value.id=='self'}=={'cfg'}
    base=ast.ClassDef(name='LanguageParent',bases=[],keywords=[],body=[parent_method],decorator_list=[])
    derived=ast.ClassDef(name='LanguageTask',bases=[ast.Name(id='LanguageParent',ctx=ast.Load())],
        keywords=[],body=[method],decorator_list=[])
    namespace={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[base,derived],type_ignores=[])),str(source),'exec'),namespace)
    return namespace['LanguageParent'],namespace['LanguageTask']


def task(task_type='loading',depth=.027,height=.0675,seat='candidate_far_hinge'):
    base,derived=language_class()
    value=derived()
    value.cfg=SimpleNamespace(env=SimpleNamespace(task_type=task_type),
        geometry=SimpleNamespace(target_depth_m=depth),vessel=SimpleNamespace(height_m=height),
        rack=SimpleNamespace(selected_slot_id='A1'),adapter=SimpleNamespace(selected_target_seat_id=seat))
    def forbidden(_):
        raise AssertionError('Task language read live or privileged state')
    for name in ('debug','_obs','scorer','ctx','robot','images','t','phase'):
        setattr(derived,name,property(forbidden))
    return base,value


def test_loading_goal_uses_nominal_config_and_inherits_existing_task_text():
    parent,value=task()
    text=value.get_task_language()
    assert text.startswith(parent.get_task_language(value))
    assert 'loading depth 27 mm' in text
    assert 'cuvette height 67.5 mm' in text
    assert '40.5 mm of the cuvette remaining above the seat entrance' in text
    assert 'candidate_far_hinge, the internal seat farther from the lid hinge' in text
    assert 'static configured task goals, not measurements' in text


def test_loading_dimensions_follow_config_instead_of_fixed_runtime_numbers():
    _,value=task(depth=.022,height=.080,seat='candidate_near_hinge')
    text=value.get_task_language()
    assert 'loading depth 22 mm' in text and 'cuvette height 80 mm' in text
    assert '58 mm of the cuvette remaining above the seat entrance' in text
    assert 'candidate_near_hinge internal seat' in text
    assert 'selected target is candidate_far_hinge' not in text
    assert 'loading depth 27 mm' not in text


@pytest.mark.parametrize('kind',['preinsert_diagnostic','grasp_hold','extract_transport'])
def test_diagnostic_task_language_is_unchanged_and_needs_no_geometry_fields(kind):
    parent,value=task(task_type=kind)
    del value.cfg.geometry
    del value.cfg.vessel
    assert value.get_task_language()==parent.get_task_language(value)


def test_prompt_v3_explains_general_contact_checks_without_oracle_or_macro():
    assert ProjectV11RobotTools.controller_metadata()['prompt_version']=='Project_v1_1.public_tools.v3'
    assert 'Perspective alignment' in SYSTEM_PROMPT
    assert 'no more than0.001m/s' in SYSTEM_PROMPT
    assert 'vessel moves upward relative to the fingers' in SYSTEM_PROMPT
    assert 'one side of finger contact is lost' in SYSTEM_PROMPT
    assert 'rather than opening early' in SYSTEM_PROMPT
    assert 'no obstacle coordinates or safe-height oracle' in SYSTEM_PROMPT
    assert '2.602' not in SYSTEM_PROMPT and '52.9375' not in SYSTEM_PROMPT
