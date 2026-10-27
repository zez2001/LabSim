# LabSim 中文入口

LabSim 当前提供固定 standard 科学实验机器人任务、完整 teacher 示范、策略 RPC、双视角采集和独立判分。

- [项目首页与完整中文快速开始](README.md)：安装、固定资产、demo、采集、读取、评测及常见问题。
- [Project_release_v1 发布入口](docs/lab_cuvette_loading/Project_release_v1/README.md)：显式版本、记录模式、本轮实际验收与遗留项。
- [Project_v1_1 物理基线](docs/lab_cuvette_loading/Project_v1_1/README.md)：执行器、控制器与历史实际验证范围。
- [开发接入](docs/development/ONBOARDING.md)：运行环境、代码地图、动作与数据契约。
- [历史版本](docs/history/README.md)：V0、ext、demo、Env、Size 与各发布版本。
- [English quick start](README_EN.md)。

长期开发分支和 GitHub 默认分支为 `codex/labsim`。省略 `--project-version` 时仍默认旧 `Project_v1`；运行新版须保留显式版本参数。Teacher 全流程成功与模型零样本任务成功分别报告。

新版预检显式运行 `./labsim doctor --project-version Project_release_v1 --json`。采集后等待进程退出，通过`demos.lab_cuvette_project_release_v1.dataset_index`为整组建立新索引，再用`dataset-check --index ... --sample-filter all_valid --policy both`检查全部三集；不能只读`episode_0000`便推断三集结果。准确命令见[中文主页](README.md#数据采集与读取)。索引默认相对链接，移动时需连同来源H5一起保留目录；`--mode copy`才创建额外的自包含副本。

原上游 LabUtopia 安装和引用说明保留在[上游文档](docs/upstream/README.labutopia.md)。原实验进展和旧分支记录可通过 Git 历史及[版本索引](docs/history/README.md)查阅，不作为当前安装步骤。
