# LabSim Size_v1 进展与分享入口

更新于2026-10-22。独立分支为[`codex/lab-cuvette-size-v1`](https://github.com/zez2001/LabSim/tree/codex/lab-cuvette-size-v1)。本轮固定原A座`candidate_far_hinge`，通过同一XY仿射规则派生比色皿尺寸，不修改原座、整机、旧资产或源CAD。

已完成35个9.50–12.50mm独立资产及几何筛选。正式任务采用10.00×10.00×67.5mm假设资产、20g质量假设，重新计算COM/惯量。10.00mm和10.30mm均有实际完整装载成功；10.50mm开发运行虽释放并撤离，抓持和对准门控仍失败，不能由末态稳定改判成功。物理可用结果只覆盖已测离散尺寸，10.70mm正几何证书不是物理上限。

固定standard验证5/5完整成功，并计入正式20条合格自然成功。另采集20条有效受控失败：1/5/10/18mm插入深度处提前停止各5条，无自然失败；没有把它们解释为自然卡滞或尺寸不可通过。全部40条通过冻结、实际事件、真实进程及正常数据读取审计；9次仿真子进程均exit0，无中断。ACT/DP成功和失败读取均通过，两组各按完整episode划分18/2，训练未执行。collect、train及自动验证均固定standard，random10取消。

- [本轮DOCX报告](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.docx) · [报告与5段实际录像](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md)
- [40条最终数据审计与读取](docs/lab_cuvette_loading/Size_v1/data/final40_actual/README.md) · [5次固定场景逐集结果及便携样例](docs/lab_cuvette_loading/Size_v1/data/standard5_actual/README.md)
- [本轮调用与范围](docs/lab_cuvette_loading/Size_v1/README.md) · [详细命令及未来训练相机配置](demos/lab_cuvette_size_v1/README.md) · [持续状态](TASK_STATUS.md)
- [35尺寸完整几何结果](docs/lab_cuvette_loading/Size_v1/geometry/family_20261021_02/README.md) · [可替换资产注册](assets/lab_cuvette_loading/Size_v1/registry.json)
- [碰撞烹饪／座表面抽样与限制](docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.md) · [冻结配置](config/lab_cuvette_loading/Size_v1/standard.yaml) · [冻结依赖](config/lab_cuvette_loading/Size_v1/frozen_scene.json)
- [本轮Agent结果快照](docs/agent_handoff/Size_v1_current/状态与边界.md) · [精简阅读包规范](docs/agent_handoff/README.md)

新阅读包为`LabSim_Size_v1_本轮改动与结果_精简阅读包_20261022`，仅包含本轮报告、必要结果媒体、结果表和配置证据。完整collection与约1.96GB独立便携episode另行管理。原座完整烹饪表示读回、原生速度与差分告警及真实物理校准仍有局限；不宣称实物尺寸或平台精度已获验证。下方保留Env_v1历史阶段原结论，不代表当前Size_v1状态。

# LabSim 进展与分享入口

历史阶段 **Env_v1 已整理为正式任务并接通三条真实策略短链，原刚性座完整装载仍受阻**。当前场景使用单台开盖仪器、完整白色6×6来源架和12.5×12.5×67.5 mm器皿，目标是腔内原A座 `candidate_far_hinge`。A/B原座保留12.6 mm中央参考截面及全部内伸结构；原尺寸直立刚性入口的整个必要XY域仍存在材料冲突，没有扩孔、删件或放宽判据。

Env_v1阶段的 **preinsert_continuous_latch01安全预插入诊断已真实通过**：82.65秒，完成清槽、悬持、搬运、原座上方安全接近、上抬和末段1秒保持；未插入、未松爪、未实际撤离，full/native_pair仍为null。此前continuous_latch01的230.445 µm漂移超限false保留。真实projection和zero_delay渲染修复已有最新4958/4958同观测关联实证，旧0.966282 mm残差是修复前记录。π0.5、GPT-6 Astra direct、真实RLinf/RPent Harness VLA各接通5动作/0.25秒短链，均task_success=false，非任务级评测。固定5次/random10次及20+20尚未开始。

- [本轮DOCX报告](docs/lab_cuvette_loading/Env_v1/results_20261021/LabSim_Env_v1_本轮进展报告.docx) · [Markdown报告与视频](docs/lab_cuvette_loading/Env_v1/results_20261021/LabSim_Env_v1_本轮进展报告.md) · [24条实际运行表](docs/lab_cuvette_loading/Env_v1/results_20261021/actual_runs.csv)
- [当前完成状态与全部调用命令](docs/lab_cuvette_loading/Env_v1/README.md) · [持续任务状态](TASK_STATUS.md)
- [预览及受门控standard/random入口](docs/lab_cuvette_loading/Env_v1/README.md) · [正常读取筛选 便携导出 视频回看](docs/lab_cuvette_loading/Env_v1/data/README.md)
- [三策略真实调用及全部历史尝试](docs/lab_cuvette_loading/Env_v1/policy_backends.md) · [实际短链记录](docs/lab_cuvette_loading/Env_v1/policy_evidence/real_three_chain_01.json)
- [23项真实API检查](docs/lab_cuvette_loading/Env_v1/policy_evidence/live_environment_api_validation.json)（random仅初始化，非正式任务批次）
- [15周期真实动作回放](docs/lab_cuvette_loading/Env_v1/replay_README.md) · [本轮连续诊断阅读媒体来源](docs/lab_cuvette_loading/Env_v1/data/reading_media_provenance.json)（不代表完整装载）
- [原座几何与最少实物信息](docs/lab_cuvette_loading/Env_v1/geometry/README.md) · [提取力与姿态图](docs/lab_cuvette_loading/Env_v1/data/extract01_control_alignment.png) · [动态相机残差](docs/lab_cuvette_loading/Env_v1/data/extract01_renderer_USD_dynamic_audit.json)
- [新诊断成功结果及范围](docs/lab_cuvette_loading/Env_v1/data/preinsert_continuous_latch01_result_summary.json) · [当前资产 变换与尺寸清单](docs/lab_cuvette_loading/Env_v1/current_asset_scene_manifest.json)
- [全部历史版本](LABSIM_PROGRESS.md) · [V0_demo04历史报告](docs/lab_cuvette_loading/V0_demo04/report.md) · [精简Agent阅读包规则](docs/agent_handoff/README.md)

分享分支为 [`codex/lab-cuvette-env-v1`](https://github.com/zez2001/LabSim/tree/codex/lab-cuvette-env-v1)。源CAD、旧资产和结果保留。每轮新阅读包只收本轮改动、报告和少量结果媒体，不默认收整个工程或原始H5；本轮报告已生成并完成8页渲染核查。按最终推送提交生成的桌面小阅读包为 `LabSim_Env_v1_本轮改动与结果_精简阅读包_20261021`，包含报告、三段实际诊断/失败视频、CSV与配置；完整2546460010字节数据单独存放，最终提交和SHA见包根清单。真实校准仍为false，诊断成功不进入完整装载成功BC。以下保留上游LabUtopia文档。

<div align="center">
  <img src="images/logo.png" alt="Logo" width="180">
</div>

# [NeurIPS 2025] LabUtopia: High-Fidelity Simulation and Hierarchical Benchmark for Scientific Embodied Agents

<div align="center">

[![Paper](https://img.shields.io/badge/📄_Paper-arXiv-red.svg)](https://arxiv.org/pdf/2505.22634v1.pdf)
[![arXiv](https://img.shields.io/badge/arXiv-2505.22634-b31b1b.svg)](https://arxiv.org/abs/2505.22634)
[![Website](https://img.shields.io/badge/🌐_Website-LabUtopia-blue.svg)](https://rui-li023.github.io/labutopia-site/)
[![Dataset](https://img.shields.io/badge/HuggingFace-Dataset-orange?logo=huggingface)](https://huggingface.co/datasets/Ruinwalker/Labutopia-Dataset)

</div>

<div align="center">
  <img src="images/teaser.png" alt="LabUtopia Teaser" width="80%">
</div>

[中文版 README](README_CN.md) | [English README](README.md)

## System Requirements
- NVIDIA GPU with CUDA support (RTX series recommended, Isaac Sim does not support A100/A800)
- Ubuntu 24.04 (tested version)
- conda
- Python 3.11
- Isaac Sim 5.1

## 🛠️ Installation

### 1. Code Download

Download the code and pull scene assets:

```bash
git clone https://github.com/Rui-li023/LabUtopia.git
sudo apt install git-lfs 
git lfs pull
```

### 2. Environment Creation
Create and activate a new conda environment:
```bash
conda create -n labutopia python=3.11 -y
conda activate labutopia
```

### 3. Dependencies Installation
Install required packages:
```bash
# Install PyTorch
pip install torch==2.9.0 torchvision==0.24.0 torchaudio==2.9.0 --index-url https://download.pytorch.org/whl/cu126

# Install Isaac Sim
pip install isaacsim[all,extscache]==5.1.0 --extra-index-url https://pypi.nvidia.com

# Install other dependencies
pip install -r requirements.txt

# Run script to setup .vscode/settings.json
python -m isaacsim --generate-vscode-settings
```

## Code Structure

```
LabSim/
├── assets/                # Resource files directory
│   ├── chemistry_lab/     # Chemistry lab scene resources
│   ├── fetch/             # Fetch robot resources
│   ├── navigation/        # Navigation task resources
│   └── robots/            # Robot model resources
├── config/                # Configuration files directory
│   ├── level1_*.yaml    # Level 1 basic task configs
│   ├── level2_*.yaml    # Level 2 combined task configs
│   ├── level3_*.yaml    # Level 3 generalization task configs
│   └── level4_*.yaml    # Level 4 long sequence task configs
├── controllers/         # Controller implementations
│   ├── atomic_actions/  # Basic action controllers
│   ├── inference_engines/ # Inference engine implementations
│   └── robot_controllers/ # Robot controllers
├── data_collectors/     # Data collector implementations
├── factories/           # Factory class implementations
├── policy/            # Policy model implementations
├── tasks/             # Task definition implementations
├── tests/            # Test code
└── utils/            # Utility functions
```

### Design Philosophy
1. Modular structure for better code organization and maintainability
2. Scene state and observation data acquisition (including camera images, robot states, and scene object states) are handled in tasks
3. Robot control and task success condition checking are handled in controllers

## Usage

### Data Collection

Data collection is the first step in training models. LabUtopia supports data collection for multiple task types, and you can also download pre-collected data from our HuggingFace repository.

#### 1. Select Configuration File
There are multiple pre-configured task files in the `config` folder:

**Level 1 Basic Tasks:**
- `level1_pick.yaml` - Pick tasks
- `level1_place.yaml` - Place tasks  
- `level1_open_door.yaml` - Open door tasks
- `level1_open_drawer.yaml` - Open drawer tasks
- `level1_close_door.yaml` - Close door tasks
- `level1_close_drawer.yaml` - Close drawer tasks
- `level1_pour.yaml` - Pour tasks
- `level1_press.yaml` - Press tasks
- `level1_shake.yaml` - Shake tasks
- `level1_stir.yaml` - Stir tasks

**Level 2 Combined Tasks:**
- `level2_ShakeBeaker.yaml` - Shake beaker
- `level2_StirGlassrod.yaml` - Stir with glass rod
- `level2_PourLiquid.yaml` - Pour liquid
- `level2_TransportBeaker.yaml` - Transport beaker
- `level2_Heat_Liquid.yaml` - Heat liquid
- `level2_openclose.yaml` - Open and close tasks

**Level 3 Generalization Tasks:**
- `level3_PourLiquid.yaml` - Complex pour tasks
- `level3_Heat_Liquid.yaml` - Complex heating tasks
- `level3_TrabsportBeaker.yaml` - Complex transport tasks
- `level3_open.yaml` - Complex open tasks
- `level3_pick.yaml` - Complex pick tasks
- `level3_press.yaml` - Complex press tasks

**Level 4 Long Sequence Tasks:**
- `level4_CleanBeaker.yaml` - Clean beaker
- `level4_DeviceOperation.yaml` - Device operation

#### 2. Modify Configuration Parameters

Each configuration file contains the following main parameters that need to be adjusted according to requirements:

```yaml
# Basic configuration
name: level1_pick                    # Task name
task_type: "pick"                   # Task type
controller_type: "pick"             # Controller type
mode: "collect"                     # Mode: collect or infer

# Scene configuration
usd_path: "assets/chemistry_lab/pick_task/scene.usd"  # Scene file path

# Task parameters
task:
  max_steps: 1000                   # Maximum steps
  obj_paths:                        # Target object configuration
    - path: "/World/conical_bottle02"
      position_range:               # Object position range
        x: [0.22, 0.32]
        y: [-0.07, 0.03]
        z: [0.80, 0.80]

# Data collection parameters
max_episodes: 100                   # Maximum collection episodes

# Camera configuration
cameras_names: ["camera_1", "camera_2"]
cameras:
  - prim_path: "/World/Camera1"
    name: "camera_1"
    translation: [2, 0, 2]         # Camera position
    resolution: [256, 256]         # Resolution
    focal_length: 6                 # Focal length
    orientation: [0.61237, 0.35355, 0.35355, 0.61237]  # Orientation
    image_type: "rgb"              # Image type, rgb depth, point. You can use rgb+depth to get more than one type of image.

# Robot configuration
robot:
  type: "franka"                   # Robot type
  position: [-0.4, -0, 0.71]      # Robot position

# Data collector configuration
collector:
  type: "default"                  # Collector type
  compression: null                # Compression settings
```

#### 3. Run Data Collection

After selecting the configuration file, run:
```bash
# Use default configuration
python main.py --config-name level1_pick
```

Data will be saved in the `outputs/collect/date/time_taskname/` directory.

### Training

The training process uses collected data to train robot policy models.

#### 1. Select Training Configuration

There are multiple training configurations in the `policy/config/` folder:

- `train_diffusion_unet_image_workspace.yaml` - Diffusion model training (recommended)
- `train_act_image_workspace.yaml` - ACT model training

#### 2. Modify Training Parameters

Main parameters that need to be adjusted:

```yaml
# Model configuration
policy:
  _target_: policy.policy.diffusion_unet_image_policy.DiffusionUnetImagePolicy
  shape_meta: ${shape_meta}        # Data shape metadata
  
  # Noise scheduler configuration
  noise_scheduler:
    num_train_timesteps: 100       # Training timesteps
    beta_start: 0.0001             # Beta start value
    beta_end: 0.02                 # Beta end value
    beta_schedule: squaredcos_cap_v2  # Beta schedule strategy

  # Observation encoder configuration
  obs_encoder:
    _target_: policy.model.vision.multi_image_obs_encoder.MultiImageObsEncoder
    rgb_model:
      _target_: policy.model.vision.model_getter.get_resnet
      name: resnet18               # Backbone network
    resize_shape: [256, 256]      # Resize shape
    random_crop: False              # Random crop

# Training parameters
training:
  device: "cuda:0"                # Training device
  seed: 42                        # Random seed
  num_epochs: 8000                # Training epochs
  lr: 1.0e-4                      # Learning rate
  batch_size: 64                  # Batch size
  gradient_accumulate_every: 1     # Gradient accumulation steps
  
  # Checkpoint saving
  checkpoint_every: 30             # Save every 30 epochs
  val_every: 10                   # Validate every 10 epochs

# Data loader configuration
dataloader:
  batch_size: 64                  # Batch size
  num_workers: 4                  # Number of workers
  shuffle: True                   # Whether to shuffle data

# Optimizer configuration
optimizer:
  _target_: torch.optim.AdamW
  lr: 1.0e-4                      # Learning rate
  betas: [0.95, 0.999]           # Adam parameters
  weight_decay: 1.0e-6           # Weight decay
```

#### 3. Specify Dataset Location
Modify the corresponding configuration file in the `policy/config/task` folder, change the `dataset_path` parameter to your dataset folder location.

#### 4. Run Training

```bash
# Use diffusion model training
python train.py --config-name=train_diffusion_unet_image_workspace

# Use ACT model training
python train.py --config-name=train_act_image_workspace
```

Training logs and models will be saved in the `outputs/train/date/time_modelname_taskname/` directory.

### Inference

Use trained models for inference testing.

#### 1. Modify Configuration File

Change the mode from `collect` to `infer` in the configuration file and add inference-related configurations:

```yaml
# Basic configuration
mode: "infer"                     # Change to inference mode

# Inference configuration
infer:
  obs_names: {"camera_1_rgb": 'camera_1_rgb', "camera_2_rgb": 'camera_2_rgb'}
  
  # Local inference configuration
  policy_model_path: "outputs/train/2025.03.25/12.43.59_train_act_image_pick_pick_data/checkpoints/latest.ckpt"
  policy_config_path: "outputs/train/2025.03.25/12.43.59_train_act_image_pick_pick_data/.hydra/config.yaml"
  normalizer_path: "outputs/train/2025.03.25/12.43.59_train_act_image_pick_pick_data/checkpoints/normalize.ckpt"
  
  # Remote inference configuration (optional)
  type: "remote"                  # Use remote inference
  host: "101.126.156.90"         # Server address
  port: 56434                     # Server port
  n_obs_steps: 1                  # Observation steps
  timeout: 30                     # Timeout
  max_retries: 3                  # Maximum retries

max_episodes: 50                  # Inference episodes
```

#### 2. Run Inference

```bash
# Use local model inference
python main.py --config-name level1_pick

# Use remote inference
python main.py --config-name level3_PourLiquid
```

Inference results will be saved in the `outputs/infer/date/time_taskname/` directory.

## Use OpenPI

### Installation

Download our modified OpenPI code:

```
git clone https://github.com/Rui-li023/openpi.git
```

### Data Conversion

Convert LabUtopia format data to LeRobot format dataset:

```
python scripts/convert_labsim_data_to_lerobot.py --data_dir outputs/collect/xxx/xxx/dataset --num_processes 8 --fps 60 --repo_name labutopia/level3-pick
```

**Note:** The `--fps` argument specifies the control frequency of the converted data. Our collected demonstrations are sampled at 60Hz by default. If you want the converted dataset to have the same behavior as the original collection, make sure to set `--fps` to 60.

### Remote Inference

LabUtopia supports using remote servers for model inference.

#### Installation

```
cd openpi/packages/openpi-client
pip install -e . 
```

#### Configuration
Configure the remote inference engine in your config file:

```yaml
infer:
  engine: remote  # Use remote inference engine
  host: "0.0.0.0"  # OpenPI server host
  port: 8080  # OpenPI server port (optional)
  n_obs_steps: 3  # Observation steps
```

#### Usage
The OpenPI client provides simplified WebSocket communication with the remote server:

1. **Initialize**: The client automatically connects to the OpenPI server using WebSocket
2. **Inference**: Sends observation data (images, poses) to the server and receives action predictions
3. **Data Format**: Automatically handles image format conversion and pose data serialization
4. **Error Handling**: Includes fallback mechanisms for failed predictions

#### Server Response Format
The OpenPI server should return actions in one of these formats:
- `{"action": [action_array]}`
- `{"actions": [action_array]}`
- Any dictionary with a key containing "action"

## 🤝 Contributing

We welcome contributions from the community! If you have any questions, suggestions, or ideas for improvements, please feel free to:

- **Open an Issue**: Report bugs, request features, or discuss ideas
- **Submit a Pull Request**: Contribute code improvements, documentation fixes, or new features

Before submitting a PR, please ensure your code follows the project's coding style and passes relevant tests.

Thank you to all contributors for supporting this project! 🙏

## 📚 Citation

```bibtex
@article{li2025labutopia,
  author    = {Li, Rui and Hu, Zixuan and Qu, Wenxi and Zhang, Jinouwen and Yin, Zhenfei and Zhang, Sha and Huang, Xuantuo and Wang, Hanqing and Wang, Tai and Pang, Jiangmiao and Ouyang, Wanli and Bai, Lei and Zuo, Wangmeng and Duan, Ling-Yu and Zhou, Dongzhan and Tang, Shixiang},
  title     = {LabUtopia: High-Fidelity Simulation and Hierarchical Benchmark for Scientific Embodied Agents},
  journal   = {arXiv preprint arXiv:2505.22634},
  year      = {2025},
}
```

## 📄 License
This repository contains both source code and data assets:

- **Code**  
  Released under the [MIT License](./LICENSE).  

- **Data Assets**  
  Released under the [CC BY-NC 4.0 License](https://creativecommons.org/licenses/by-nc/4.0/).  
  Free to use and modify for research and educational purposes **only**.  
