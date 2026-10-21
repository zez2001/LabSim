"""Refresh only the small Size_v1 reading snapshot, without simulation/packaging.

Final quotas come only from an explicitly supplied actual collection audit.
No DOCX, video, HDF5, archive, asset, label or final desktop package is created.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/agent_handoff/Size_v1_current"
FAMILY = ROOT / "docs/lab_cuvette_loading/Size_v1/geometry/family_20261021_02"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def refresh(*, summary=None, collection_audit=None, allow_refresh=False):
    if OUT.exists() and not allow_refresh:
        raise FileExistsError("Existing Size_v1 current snapshot requires explicit --refresh")
    OUT.mkdir(parents=True, exist_ok=True)
    provenance = []
    def copy(source, target):
        source, target = Path(source), OUT / target
        if not source.is_file():
            raise FileNotFoundError(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = sha(source)
        if sha(target) != digest:
            raise RuntimeError("Snapshot copy differs from source")
        provenance.append(dict(source=str(source.relative_to(ROOT)), copy=str(target.relative_to(OUT)),
                               source_sha256=digest, copy_sha256=digest, bytes=target.stat().st_size))
    def save(name, value):
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")

    copy(ROOT / "config/lab_cuvette_loading/Size_v1/standard.yaml", "configs/standard.yaml")
    copy(ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json", "configs/frozen_scene.json")
    for policy in ("act", "dp"):
        copy(ROOT / f"policy/config/task/lab_cuvette_size_v1_{policy}.yaml", f"configs/dataset/lab_cuvette_size_v1_{policy}.yaml")
    sources = {
        FAMILY / "candidate_dimensions_and_geometry.csv": "candidate_dimensions_and_geometry.csv",
        FAMILY / "family_summary.json": "geometry_family_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.json": "cooked_preview01_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.md": "cooked_preview01_summary.md",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/freeze_against_first_success.json": "freeze_against_first_success.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/phase_A_cpu_validation.json": "phase_A_cpu_validation.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/normal_reader_directory_filename_cpu_check.json": "normal_reader_directory_filename_cpu_check.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/camera_actual_config_summary.json": "development_camera_actual_config_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/normal_read_success_filter.json": "development_success_normal_read.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/frozen_reader_admission_actual.json": "development_frozen_admission.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/independent_recomputed_score.json": "development_independent_recomputed_score.json",
    }
    for source, target in sources.items():
        copy(source, target)
    # Prefer the individually CLOSED official first episode over development
    # metadata. Never open the currently recording episode2+ or read its HDF5.
    formal_inspection = ROOT / "docs/lab_cuvette_loading/Size_v1/data/standard01_inspection"
    guarded_path = formal_inspection / "guarded_frozen_dataset_read.json"
    readability_path = formal_inspection / "standard01_readability_summary.json"
    formal_evidence, derived_sources = None, []
    if guarded_path.is_file() and readability_path.is_file():
        guarded, readability = read(guarded_path), read(readability_path)
        episode = Path(guarded["source_episode"]).resolve()
        frozen_sha = read(ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json")["frozen_scene_sha256"]
        if not episode.is_relative_to(ROOT / "outputs/lab_cuvette_loading/Size_v1/collection_standard/runs") or episode.name != "episode_0000":
            raise ValueError("Formal camera/initial evidence must refer only to closed official episode0")
        final = read(episode / "result.json")
        if final.get("complete") is not True or readability.get("individually_closed_complete_record") is not True or readability.get("accessible_write_handles_to_episode"):
            raise ValueError("Formal first episode is not proven individually closed")
        if guarded.get("frozen_scene_sha256") != frozen_sha or guarded.get("source_metadata", {}).get("frozen_scene_sha256") != frozen_sha or readability.get("episode_id") != final.get("episode_id"):
            raise ValueError("Formal closed-episode frozen fingerprint or identity differs")
        copy(guarded_path, "formal_standard01/guarded_frozen_dataset_read.json")
        copy(readability_path, "formal_standard01/standard01_readability_summary.json")
        copy(episode / "physics_capture_meta.json", "formal_standard01/physics_capture_meta.json")
        copy(episode / "reset_check.json", "formal_standard01/reset_check.json")
        if (formal_inspection / "closed_episode_writer_preflight.json").is_file():
            copy(formal_inspection / "closed_episode_writer_preflight.json", "formal_standard01/closed_episode_writer_preflight.json")
        camera = dict(schema="labsim.Size_v1.formal_closed_episode_camera_summary.v1",
            source_episode=str(episode), episode_id=final["episode_id"], frozen_scene_sha256=frozen_sha,
            scope="Actual individually closed frozen standard episode0; batch-exit/quota status is separate",
            configured_cameras=readability["configured_camera_snapshot"], actual_mounts=readability["actual_camera_mounts"],
            actual_observation_count=readability["actual_observation_count"], continuous_side_and_wrist=True,
            observed_camera_checks=readability["cameras"],
            real_calibrated=False, source_labels_modified=False,
            renderer_association_is_not_real_precision=True)
        save("camera_actual_config_summary.json", camera)
        initial_path = episode / "initial_debug.json"
        initial = read(initial_path)
        initial_fields = ("t", "simulation_time", "engine_time", "physics_step", "phase", "object_position_m",
            "object_quaternion_wxyz", "com_world_m", "source_bottom_z_m", "source_bottom_gap_m",
            "source_rack_penetration_m", "target_bottom_gap_m", "depth_m", "xy_error_target_m",
            "tilt_deg", "yaw_error_deg", "joints9", "joint_velocities9", "actual_tcp_position_m",
            "actual_tcp_quaternion_wxyz", "linear_velocity_native_m_s", "angular_velocity_native_rad_s",
            "linear_velocity_USD_m_s", "angular_velocity_USD_deg_s", "fd_com_velocity_m_s",
            "fd_angular_velocity_rad_s", "finger_contact_N")
        initial_summary = dict(schema="labsim.Size_v1.formal_initial_state_small_summary.v1",
            source_episode=str(episode), episode_id=final["episode_id"], frozen_scene_sha256=frozen_sha,
            source_initial_debug_sha256=sha(initial_path),
            scope="Saved actual first public reset observation after recorded initialization physics steps; not a substitute for the full early physics trace",
            actual={key: initial.get(key) for key in initial_fields},
            declared_initial_joints=read(episode / "declared_initial_joints.json"),
            reset_check=read(episode / "reset_check.json"),
            source_labels_or_states_modified=False)
        save("formal_standard01/initial_state_summary.json", initial_summary)
        formal_evidence = dict(episode_id=final["episode_id"], source_episode=str(episode),
            frozen_scene_sha256=frozen_sha, individually_closed=True,
            task_success=final.get("task_success"), release_observed=final.get("release_observed"),
            retreat_observed=final.get("retreat_observed"), stable_after_retreat=final.get("stable_after_retreat"),
            actual_control_steps=final.get("actual_control_steps"),
            scope="Individual physical and guarded dataset read evidence; official whole-process exit and final quota remain separate")
        for source, target in ((readability_path, "camera_actual_config_summary.json"),
                               (initial_path, "formal_standard01/initial_state_summary.json")):
            derived_sources.append(dict(source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                derived_file=target, derived_sha256=sha(OUT / target)))
    else:
        copy(ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/camera_actual_config_summary.json",
             "camera_actual_config_summary.json")
    registry_path = ROOT / "assets/lab_cuvette_loading/Size_v1/registry.json"
    registry = read(registry_path)
    selected_fields = ("asset_id", "asset_path", "asset_sha256", "source", "builder", "derivation_method",
        "axis_scale", "nominal_outer_xy_mm", "actual_outer_dimensions_mm", "height_nominal_mm", "datum",
        "default_prim", "meters_per_unit", "up_axis", "mass_kg", "mass_source", "mass_distribution_assumption",
        "mass_properties", "reloaded_mass_properties", "checks", "inner_cavity_sections", "real_calibrated")
    assets = [{key: value.get(key) for key in selected_fields}
              for value in sorted(registry["assets"].values(), key=lambda v: v["asset_id"])]
    save("asset_summary.json", dict(schema="labsim.Size_v1.compact_asset_summary.v1",
        source_registry=str(registry_path.relative_to(ROOT)), source_registry_sha256=sha(registry_path),
        asset_count=len(assets), assets=assets, USD_asset_files_included=False,
        collision_input="28 thick-wall convex input meshes; same XY affine as visual geometry; original seat unchanged",
        omission="Full collision attribute dump and geometry arrays stay in repository registry/USD, not this small reading snapshot"))
    quota = dict(status="unavailable_no_explicit_final_collection_audit", qualified_success_count=None,
        qualified_failure_count=None, success_target=20, failure_target=20,
        success_missing=None, failure_missing=None, condition_groups=None, evidence=None)
    if collection_audit:
        audit = read(collection_audit)
        if audit.get("schema") != "labsim.Size_v1.collection_audit.v1":
            raise ValueError("Expected the actual Size_v1 collection audit, not a driver plan or raw score")
        if audit.get("official_collection_quota_evidence") is not True:
            raise ValueError("Standalone episode reads do not establish official20/20 collection quotas")
        frozen = read(ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json")
        if audit.get("frozen_scene_sha256") != frozen["frozen_scene_sha256"]:
            raise ValueError("Final collection audit belongs to a different frozen scene")
        quota.update(status="actual_collection_audit", **{key: audit.get(key) for key in
            ("qualified_success_count", "qualified_failure_count", "success_missing", "failure_missing", "condition_groups")},
            evidence=dict(source=str(Path(collection_audit).resolve()), sha256=sha(collection_audit)))
        copy(collection_audit, "final_collection_audit.json")
    actual_runs = []
    source_results = sorted((ROOT / "outputs/lab_cuvette_loading/Size_v1").glob("**/episode_*/result.json"))
    fields = ("episode_id", "asset_id", "scene_version", "task_type", "complete", "record_valid", "task_success",
        "full_success", "failure_type", "termination_reason", "condition_group", "frozen_scene_sha256",
        "actual_control_steps", "actual_physics_steps", "simulation_seconds", "wall_seconds", "release_observed",
        "retreat_observed", "stable_after_retreat", "source_slot_cleared", "grasp_success", "transport_success",
        "post_retreat_window", "physics_quality_flags")
    for path in source_results:
        result = read(path)
        if result.get("complete") is not True:
            continue
        actual_runs.append(dict(source=str(path.relative_to(ROOT)), source_sha256=sha(path),
            **{key: result.get(key) for key in fields},
            qualification="Use explicit final collection audit; closed raw result alone does not establish frozen quota admission"))
    combined = read(summary) if summary else None
    if summary:
        if combined.get("schema") != "labsim.Size_v1.combined_results.v1":
            raise ValueError("Unsupported combined result summary")
        for source in sorted(Path(summary).parent.glob("*.csv")):
            copy(source, "result_tables/" + source.name)
    verification_path = ROOT / "outputs/lab_cuvette_loading/Size_v1/collection_standard/verify5_passed.json"
    verification = read(verification_path) if verification_path.is_file() else dict(passed=None,
        status="No closed official5/5 pass evidence at snapshot time; may be running or not passed")
    if verification_path.is_file():
        copy(verification_path, "verify5_passed.json")
    snapshot = dict(schema="labsim.Size_v1.small_reading_results.v1", version="Size_v1",
        generated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        actual_closed_raw_results=actual_runs, raw_result_labels_modified=False,
        observed_development_or_official_full_successes=sum(row.get("full_success") is True for row in actual_runs),
        official_verify5=verification, qualified_collection=quota,
        formal_first_closed_episode_evidence=formal_evidence,
        combined_summary_source=None if not summary else dict(path=str(Path(summary).resolve()), sha256=sha(summary)),
        scope="Raw closed task outcomes, official repeat evidence and strict frozen collection quotas are separate",
        random10_required=False, real_calibrated=False)
    save("result_snapshot.json", snapshot)
    save("data_qualification.json", dict(schema="labsim.Size_v1.reading_data_qualification.v1",
        **quota, train_default_filter="eligible complete successful full-loading episodes only",
        train_validation_split="whole episode; same frozen standard scene on both sides",
        natural_and_controlled_failures_separate=True, labels_modified=False,
        scene_modes=dict(collect="standard", train="standard", automatic_validation="standard", future_eval_random="explicit only"),
        random10_required=False, full_native_H5_in_reading_package=False,
        relative_index="collection_standard/dataset/episode_data.hdf5 uses relative ExternalLink; move entire collection tree",
        portable_episode="Separate native original HDF5 episode export; must not be confused with lightweight index"))
    (OUT / "状态与边界.md").write_text(
        "# Size_v1 状态与边界\n\n"
        "原目标为同一A座candidate_far_hinge，原座几何及物理配置不变。35个比色皿尺寸假设使用同一XY仿射、Z高度67.5mm和固定20g质量假设；质心惯量重算，不声称真实校准。\n\n"
        f"快照观察到 {len(actual_runs)} 条已落盘complete原始结果，其中full_success=true为 {snapshot['observed_development_or_official_full_successes']} 条；这不是正式配额。"
        f"正式固定5次通过字段为 {verification.get('passed')}，合格采集成功/失败分别为 {quota['qualified_success_count']}/{quota['qualified_failure_count']}；None表示缺实际审计。逐次结果见result_snapshot.json。\n\n"
        "formal_standard01保存已单独闭合正式首集的物理记录定义、冻结读取证据和实际初态；camera_actual_config_summary优先采用该正式首集，而development_camera_actual_config_summary保留开发对照。首集完整不代表整批已退出或5/5成立。\n\n"
        "10.70mm是最大已采样正的保守完整路径证书；10.72–11.00mm完整路径未知，11.02mm及以上仅在声明直立四方位和平移规则下入口排除。不能将10mm可完成反推为实物尺寸。\n\n"
        "成功必须实际释放、脱指撤离及3秒稳定；preview、开发成功但无冻结H5指纹、短接口诊断、预检/初始化/服务失败与进程中断不填20/20配额。自然失败和确定性动作偏差分组。\n\n"
        "原生速度与差分仍可能有告警，静态完整烹饪网格/所有回退无法完全读取；逐块约14μm抽样差和原座约44.7nm射线面差不是全局界或真实精度。相机安装固定并记录实际参数；控制器使用器皿真值。\n\n"
        "collect/train/自动验证均standard，训练RNG种子单独配置；random10已取消。原12.5mm配套冲突结论与real_calibrated=false保留，原历史目录/阅读包不覆盖。\n", encoding="utf-8")
    (OUT / "复现与数据读取.md").write_text('''# 复现与数据读取

以下命令在工程根目录执行，仿真默认GUI；需要后台运行时显式加`--headless`。新输出目录必须不存在，单GPU顺序运行。

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher \\
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \\
 --output outputs/lab_cuvette_loading/Size_v1/NEW_SINGLE_RUN
```

选择已注册的其他尺寸可加`--asset-id cuvette_xy_1050`，但必须重新通过其几何及物理检查，不能继承10mm成功。原座保持不变。

正式固定验证和采集：

```bash
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/collection_standard --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase success --collection outputs/lab_cuvette_loading/Size_v1/collection_standard \\
 --allow-after-verified-five --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase controlled_failure --collection outputs/lab_cuvette_loading/Size_v1/collection_standard \\
 --allow-after-verified-five --headless
```

verify5必须新目录且5/5真实完整成功；后两阶段需显式审阅后放行。此后自然成功采集与受控失败可以交错，优先保留自然失败；不要求先满20条成功。可以先用`--phase controlled_failure --episodes-per-process 1 --max-processes 1 --allow-after-verified-five`完成1条真实任务的INSERT提前停，验证失败元数据及读取链路，再补其余数据。这条按实际提前停状态独立判分，不是缩短接口预算；若累计失败尚未满20，driver阶段退出2表示配额未满，实际单集结果另查独立评分。控制失败用固定INSERT停止深度1/5/10/18mm补充，记录完整偏差spec；只改动作，无场景随机化。各进程真实wait退出后才归档日志。非零仿真子进程退出（含143）保守单列，不能伪称exit0。

闭合后审计并建立轻索引（FINAL_AUDIT.json也必须新路径）：

```bash
../labutopia-env/bin/python scripts/validate_lab_cuvette_size_v1_data.py \\
 outputs/lab_cuvette_loading/Size_v1/collection_standard \\
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \\
 --frozen-scene config/lab_cuvette_loading/Size_v1/frozen_scene.json \\
 --index outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset/episode_data.hdf5 \\
 --output-json outputs/lab_cuvette_loading/Size_v1/collection_standard/FINAL_AUDIT.json
```

标准索引文件名固定为`collection_standard/dataset/episode_data.hdf5`。正常读取器接收dataset目录后固定追加`episode_data.hdf5`，不会自动发现名为`index.hdf5`的文件；请按上面的准确文件名创建。默认索引是同collection树内的相对H5外链，传输时必须移动整个collection树；原episode H5本身仍独立。`--copy-data`显式复制完整数据，需额外磁盘。ACT/DP任务配置默认准确指向上述collection_standard/dataset。训练成功BC默认success，失败用于单独分析，train/val按完整episode拆分、两者同一固定场景。

```bash
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \\
 outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset \\
 --sample-filter success --policy-type act
```

本轮不执行模型训练。训练入口的task配置为`lab_cuvette_size_v1_act`或`lab_cuvette_size_v1_dp`，启用冻结守卫，自动验证standard；training.seed只控制训练随机数，不允许开启场景随机化。

创建或重新生成资产/几何会改变注册与冻结依赖，应在新的版本目录进行，不能在已冻结采集时回写。生成器入口：`demos.lab_cuvette_size_v1.build_assets --widths-mm ... --directory NEW_ASSET_DIRECTORY`；几何扫描入口：`demos.lab_cuvette_size_v1.scan_family --config ... --output NEW_DIRECTORY --geometry-site ...`。均通过现有`demos/lab_cuvette_external/usd_python.sh`启动USD环境。
''', encoding="utf-8")
    save("version.json", dict(schema="labsim.Size_v1.reading_snapshot_provenance.v1", version="Size_v1",
        branch=subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        source_head_before_final_delivery_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        generated_at=snapshot["generated_at"], copies=provenance,
        derived_evidence_sources=derived_sources,
        registry_source=dict(path=str(registry_path.relative_to(ROOT)), sha256=sha(registry_path)),
        final_delivery_commit="Read final package-root 文件清单.json; do not predict a self-referential future SHA",
        final_desktop_package_created=False, DOCX_created=False, GPU_started=False))
    return dict(output=str(OUT), files=len(list(OUT.rglob("*"))), total_bytes=sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()),
        formal_success=quota["qualified_success_count"], formal_failure=quota["qualified_failure_count"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--collection-audit", type=Path)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh(summary=args.summary, collection_audit=args.collection_audit,
                             allow_refresh=args.refresh), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
