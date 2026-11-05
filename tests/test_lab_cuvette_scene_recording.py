"""CPU record identity fixtures; these are not physical scene run evidence."""
import json
from pathlib import Path

import h5py
import pytest
from omegaconf import OmegaConf

from demos.lab_cuvette_project_release_v1.scene_recording import scene_metadata
from demos.lab_cuvette_project_release_v1.scene_suite import select_scene, SUITE_VERSION
from tests.test_lab_cuvette_project_release_lifecycle import collector, transition, score

ROOT = Path(__file__).resolve().parents[1]


def selected(scene='standard'):
    cfg = select_scene(OmegaConf.load(ROOT/'config/lab_cuvette_loading/Project_release_v1/standard.yaml'), scene)
    cfg.release.record_purpose = 'policy_evaluation'
    cfg.scene_execution = dict(suite_run_id='cpu-fixture', scene_repetition_index=2, suite_episode_index=7)
    return cfg


@pytest.mark.parametrize('scene', ['standard', 'random_003'])
def test_scene_attrs_embedded_json_and_configuration_agree_through_publication(tmp_path, scene):
    cfg = selected(scene)
    c = collector(tmp_path)
    c.configuration = OmegaConf.to_container(cfg, resolve=True)
    c.begin_episode(0, episode_id='scene-record')
    transition(c)
    labels = c.finish_episode({}, score(c))
    assert labels['task_success'] is True  # unchanged independent fixture qualification
    with h5py.File(c.path) as f:
        from demos.lab_cuvette_project_release_v1.scene_data import scene_identity
        identity = scene_identity(f)
        assert identity['scene_id'] == scene
        assert identity['scene_suite_version'] == SUITE_VERSION
        assert f.attrs['scene_repetition_index'] == 2
        assert f.attrs['suite_episode_index'] == 7
        assert bool(f.attrs['fixed_collection_eligible']) == (scene == 'standard')
        embedded = json.loads(f['episode_metadata_json'].asstr()[()])
        for key, value in scene_metadata(c.configuration).items():
            assert embedded[key] == value
            assert f.attrs[key] == value


def test_begin_cannot_override_declared_scene_before_creating_episode(tmp_path):
    c = collector(tmp_path)
    c.configuration = OmegaConf.to_container(selected('random_003'), resolve=True)
    with pytest.raises(ValueError, match='scene identity'):
        c.begin_episode(0, episode_id='forged', metadata=dict(scene_id='standard'))
    assert c.file is None


@pytest.mark.parametrize('purpose', ['demonstration', 'lifecycle_diagnostic', 'resource_probe'])
def test_random_records_cannot_declare_non_evaluation_purpose(purpose):
    cfg = selected('random_003')
    cfg.release.record_purpose = purpose
    with pytest.raises(ValueError, match='policy_evaluation'):
        scene_metadata(cfg)


def test_unknown_or_tampered_fixed_definition_is_rejected():
    cfg = selected('random_003')
    cfg.scene_suite.scene_definition_sha256 = 'f' * 64
    with pytest.raises(ValueError, match='registered fixed instance'):
        scene_metadata(cfg)


def test_fixed_scene_cannot_change_via_reset_options():
    from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
    task = LabCuvetteProjectRelease.__new__(LabCuvetteProjectRelease)
    task.base_cfg = selected('random_003')
    task._finalization_error = {'old': True}
    with pytest.raises(ValueError, match='fixed scene'):
        task.reset(0, dict(scene_id='random_004'))
    assert task._finalization_error == {'old': True}


def test_runtime_execution_ordinals_are_validated():
    cfg = selected()
    cfg.scene_execution.scene_repetition_index = -1
    with pytest.raises(ValueError, match='nonnegative integer'):
        scene_metadata(cfg)
