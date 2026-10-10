"""Use the existing DP model with obs_t -> commanded action_t alignment."""
from policy.policy.diffusion_unet_image_policy import DiffusionUnetImagePolicy


class MinimalPickDiffusionPolicy(DiffusionUnetImagePolicy):
    def predict_action(self, obs_dict):
        prediction = super().predict_action(obs_dict)
        start = self.n_obs_steps - 1
        prediction["action"] = prediction["action_pred"][:, start:start + self.n_action_steps]
        return prediction
