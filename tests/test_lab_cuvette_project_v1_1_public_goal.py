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


def task(task_type='loading',depth=.027,height=.0675,seat='candidate_far_hinge',
         translation=(0,0,.1),quaternion=(0,0,0,1),tcp_frame='right_gripper'):
    base,derived=language_class()
    value=derived()
    value.cfg=SimpleNamespace(env=SimpleNamespace(task_type=task_type),
        geometry=SimpleNamespace(target_depth_m=depth),vessel=SimpleNamespace(height_m=height),
        rack=SimpleNamespace(selected_slot_id='A1'),adapter=SimpleNamespace(selected_target_seat_id=seat),
        robot=SimpleNamespace(tcp_local_m=translation,tcp_quaternion_wxyz=quaternion,tcp_frame=tcp_frame))
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
    assert 'world pose of frame right_gripper, not the panda_hand/palm origin' in text
    assert 'translation [0.0, 0.0, 0.1] metres' in text
    assert 'quaternion [0.0, 0.0, 0.0, 1.0] in wxyz order' in text
    assert '100 mm frame-origin separation is not the whole-hand collision envelope' in text
    assert 'entire hand, fingers and held vessel in both camera views' in text


def test_loading_dimensions_follow_config_instead_of_fixed_runtime_numbers():
    _,value=task(depth=.022,height=.080,seat='candidate_near_hinge')
    text=value.get_task_language()
    assert 'loading depth 22 mm' in text and 'cuvette height 80 mm' in text
    assert '58 mm of the cuvette remaining above the seat entrance' in text
    assert 'candidate_near_hinge internal seat' in text
    assert 'selected target is candidate_far_hinge' not in text
    assert 'loading depth 27 mm' not in text


def test_static_robot_calibration_follows_config_without_normalizing_or_using_live_state():
    _,value=task(translation=(.02,-.015,.12),quaternion=(.6,.8,0,0),tcp_frame='configured_tool')
    text=value.get_task_language()
    assert 'world pose of frame configured_tool' in text
    assert 'from configured_tool coordinates into parent frame panda_hand' in text
    assert 'translation [0.02, -0.015, 0.12] metres' in text
    assert 'quaternion [0.6, 0.8, 0.0, 0.0] in wxyz order' in text
    assert '100 mm frame-origin separation' not in text
    assert 'no current object or obstacle pose, safe height or motion path' in text
    # All live/debug/robot properties on this task deliberately raise if read.
    assert 'PRIVILEGED_SENTINEL' not in text


@pytest.mark.parametrize('translation,quaternion',[
    ((0,.1),(0,0,0,1)),
    ((0,0,.1,0),(0,0,0,1)),
    ((0,0,float('nan')),(0,0,0,1)),
    ((0,0,float('inf')),(0,0,0,1)),
    (None,(0,0,0,1)),
    ((0,0,.1),(0,0,1)),
    ((0,0,.1),(0,0,0,1,0)),
    ((0,0,.1),(0,0,0,0)),
    ((0,0,.1),(0,0,0,2)),
    ((0,0,.1),(0,0,float('nan'),1)),
    ((0,0,.1),(0,0,float('inf'),1)),
    ((0,0,.1),(0,0,'invalid',1)),
])
def test_invalid_static_robot_calibration_is_rejected(translation,quaternion):
    _,value=task(translation=translation,quaternion=quaternion)
    with pytest.raises(ValueError,match='Static robot TCP'):
        value.get_task_language()


def test_empty_tcp_frame_is_rejected():
    _,value=task(tcp_frame=' ')
    with pytest.raises(ValueError,match='frame name'):
        value.get_task_language()


@pytest.mark.parametrize('kind',['preinsert_diagnostic','grasp_hold','extract_transport'])
def test_diagnostic_task_language_is_unchanged_and_needs_no_geometry_fields(kind):
    parent,value=task(task_type=kind)
    del value.cfg.geometry
    del value.cfg.vessel
    del value.cfg.robot
    assert value.get_task_language()==parent.get_task_language(value)


def test_prompt_v4_explains_static_robot_geometry_and_preserves_generic_contact_checks():
    assert ProjectV11RobotTools.controller_metadata()['prompt_version']=='Project_v1_1.public_tools.v4'
    assert 'static robot calibration in task_language' in SYSTEM_PROMPT
    assert 'do not assume the frames share an origin or orientation' in SYSTEM_PROMPT
    assert 'frame-origin offset is robot geometry, not a complete hand/finger collision envelope' in SYSTEM_PROMPT
    assert 'establish visually supported clearance before horizontal transport' in SYSTEM_PROMPT
    assert 'if clearance remains uncertain, observe or stop' in SYSTEM_PROMPT
    assert 'Perspective alignment' in SYSTEM_PROMPT
    assert 'no more than0.001m/s' in SYSTEM_PROMPT
    assert 'vessel moves upward relative to the fingers' in SYSTEM_PROMPT
    assert 'one side of finger contact is lost' in SYSTEM_PROMPT
    assert 'rather than opening early' in SYSTEM_PROMPT
    assert 'no obstacle coordinates or safe-height oracle' in SYSTEM_PROMPT
    assert '2.602' not in SYSTEM_PROMPT and '52.9375' not in SYSTEM_PROMPT
    assert '0.95085' not in SYSTEM_PROMPT and '[0.036,0.016' not in SYSTEM_PROMPT
