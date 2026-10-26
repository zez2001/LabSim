import pytest
from policy.backends.action_adapters import act_dp_joint_action


def test_dataset_finger_is_not_mistaken_for_total_opening_or_ee_delta():
    action = act_dp_joint_action([.1] * 7 + [.006],
        {'episode_id': 'e', 'observation_id': 'e:15'}, action_id='a')
    assert action['type'] == 'joint_position'
    assert action['values'] == [.1] * 7
    assert action['gripper_opening_m'] == .012
    assert action['duration_s'] == 1 / 60
    assert action['gripper_effort_limit_N'] == 8
    assert 'metadata' not in action


@pytest.mark.parametrize('values', [[0] * 7, [0] * 9, [0] * 7 + [.08],
                                  [0] * 7 + [-.001], [float('nan')] * 8])
def test_malformed_or_out_of_range_data_is_not_silently_reinterpreted(values):
    with pytest.raises(ValueError):
        act_dp_joint_action(values, {'episode_id': 'e', 'observation_id': 'e:0'}, action_id='a')
