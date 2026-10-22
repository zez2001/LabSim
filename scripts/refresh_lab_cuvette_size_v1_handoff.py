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


def compact_asset(value):
    """Keep every asset's physical parameters, without mesh vertex arrays."""
    fields = ("asset_id", "asset_path", "asset_sha256", "source", "builder", "derivation_method",
        "axis_scale", "nominal_outer_xy_mm", "actual_outer_dimensions_mm", "actual_body_bounds_m",
        "height_nominal_mm", "datum", "default_prim", "meters_per_unit", "up_axis", "mass_kg",
        "mass_source", "mass_distribution_assumption", "mass_properties", "reloaded_mass_properties",
        "checks", "inner_cavity_sections", "material_attributes", "root_rigid_body_attributes",
        "affine_max_vertex_storage_error_m", "real_calibrated", "limitations")
    result = {key: value.get(key) for key in fields}
    result["collision_input_shapes"] = []
    for shape in value.get("collision_input_shapes", []):
        entry = {key: shape.get(key) for key in ("prim", "approximation", "collision_enabled",
            "contact_offset_m", "rest_offset_m", "bounds_m")}
        entry["physical_configuration_attributes"] = {key: item for key, item in
            shape.get("configuration_attributes_excluding_vertex_arrays", {}).items()
            if key.startswith(("physics:", "physx"))}
        result["collision_input_shapes"].append(entry)
    return result


def final_audit_evidence(audit):
    """Require the new executed-event gate and real reader/split proofs.

    This only inspects a supplied closed audit JSON. It never opens an HDF5
    or treats an earlier configuration-only audit as final qualification.
    """
    controlled = []
    for row in audit.get("episodes", []):
        if row.get("failure") is not True or row.get("labels", {}).get("condition_group") != "deterministic_action_deviation":
            continue
        event = row.get("controlled_deviation_event_evidence") or {}
        if event.get("qualified") is not True or event.get("actual_event_count") != 1 or not event.get("actual_event") or not event.get("checks") or not all(item is True for item in event["checks"].values()):
            raise ValueError("Qualified controlled failures require actual teacher-event/state admission evidence")
        controlled.append(dict(episode_id=row["labels"].get("episode_id"),
            actual_event=event["actual_event"], actual_depth_m=event.get("actual_depth_m"),
            actual_event_matches_saved_state=True, checks=event["checks"],
            source_sidecar_sha256=event.get("source_sidecar_sha256")))
    reads = []
    for selection, key in (("success", "qualified_success_count"), ("failure", "qualified_failure_count")):
        if not audit.get(key, 0):
            continue
        for policy in ("act", "dp"):
            matches = [row for row in audit.get("reader_validation", [])
                if row.get("sample_filter") == selection and row.get("policy_type") == policy]
            if len(matches) != 1:
                raise ValueError("Final audit requires normal ACT/DP reader validation for each admitted group")
            row = matches[0]
            train, validation = row.get("train_episode_ids"), row.get("validation_episode_ids")
            if train is None or validation is None or set(train) & set(validation) or row.get("episode_split_disjoint") is not True or row.get("train_and_validation_same_frozen_standard_scene") is not True or row.get("scene_randomization_enabled") is not False:
                raise ValueError("Final reader evidence must retain a disjoint whole-episode frozen-standard split")
            if not row.get("checks") or not all(check.get("exact_executed_actions") is True and check.get("exact_saved_RGB") is True for check in row["checks"]):
                raise ValueError("Final reader evidence lacks exact saved-action/RGB checks")
            reads.append({key: row.get(key) for key in ("sample_filter", "policy_type", "source",
                "episodes", "train_episode_ids", "validation_episode_ids", "episode_split_disjoint",
                "train_and_validation_same_frozen_standard_scene", "scene_randomization_enabled",
                "batch_shapes", "checks", "optimizer_or_training_executed")})
    return dict(schema="labsim.Size_v1.final_reader_and_actual_event_evidence.v1",
        controlled_failure_actual_events=controlled, normal_readers_and_whole_episode_splits=reads,
        source_labels_modified=False, training_executed=False)


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
    copy(ROOT / "config/lab_cuvette_loading/Size_v1/variant_evaluation_1030.yaml",
         "configs/exploration/variant_evaluation_1030.yaml")
    for policy in ("act", "dp"):
        copy(ROOT / f"policy/config/task/lab_cuvette_size_v1_{policy}.yaml", f"configs/dataset/lab_cuvette_size_v1_{policy}.yaml")
    sources = {
        FAMILY / "candidate_dimensions_and_geometry.csv": "candidate_dimensions_and_geometry.csv",
        FAMILY / "family_summary.json": "geometry_family_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.json": "cooked_preview01_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.md": "cooked_preview01_summary.md",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/freeze_against_first_success.json": "freeze_against_first_success.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/phase_A_cpu_validation.json": "phase_A_cpu_validation.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/asset_id_configuration_switch_check.json": "asset_id_configuration_switch_check.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/normal_reader_directory_filename_cpu_check.json": "normal_reader_directory_filename_cpu_check.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/runtime/future_training_hydra_compose_cpu_check.json": "future_training_hydra_compose_cpu_check.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/camera_actual_config_summary.json": "development_camera_actual_config_summary.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/normal_read_success_filter.json": "development_success_normal_read.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/frozen_reader_admission_actual.json": "development_frozen_admission.json",
        ROOT / "docs/lab_cuvette_loading/Size_v1/data/loading01_inspection/independent_recomputed_score.json": "development_independent_recomputed_score.json",
    }
    for source, target in sources.items():
        copy(source, target)
    # Small closed evidence only: the separate ~1.96GB portable episode and
    # full image/log/HDF5 assets never enter this reading snapshot.
    small_evidence = {
        "protection_audit/protection_audit.json": "protection/protection_audit.json",
        "protection_audit/original_A_seat_composed_USD_snapshot.json": "protection/original_A_seat_composed_USD_snapshot.json",
        "protection_audit/all35_asset_checks.csv": "protection/all35_asset_checks.csv",
        "protection_audit/legacy_namespace_check.json": "protection/legacy_namespace_check.json",
        "standard5_actual/portable_episode_validation.json": "portable_sample/portable_episode_validation.json",
        "standard5_actual/portable_episode_archive_validation.json": "portable_sample/portable_episode_archive_validation.json",
        "standard5_actual/standard5_initial_state_and_results.csv": "formal_verify5/initial_state_and_results.csv",
        "standard5_actual/standard5_initial_state_and_results.json": "formal_verify5/initial_state_and_results.json",
        "first_controlled_failure_actual/actual_INSERT_early_stop_event.json": "historical_closed_examples/first_actual_INSERT_early_stop_event.json",
        "first_controlled_failure_actual/config_only_deviation_negative_check.json": "historical_closed_examples/config_only_deviation_negative_check.json",
        "first_controlled_failure_actual/normal_ACT_DP_success_and_failure_read.json": "historical_closed_examples/normal_ACT_DP_success_and_failure_read.json",
        "controlled01_physics_inspection/production_event_admission_closed11.json": "historical_closed_examples/production_event_admission_closed11.json",
    }
    for relative, target in small_evidence.items():
        source = ROOT / "docs/lab_cuvette_loading/Size_v1/data" / relative
        if source.is_file():
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
    assets = [compact_asset(value) for value in sorted(registry["assets"].values(), key=lambda v: v["asset_id"])]
    save("asset_summary.json", dict(schema="labsim.Size_v1.compact_asset_summary.v1",
        source_registry=str(registry_path.relative_to(ROOT)), source_registry_sha256=sha(registry_path),
        asset_count=len(assets), assets=assets, USD_asset_files_included=False,
        collision_input="28 thick-wall convex input meshes; same XY affine as visual geometry; original seat unchanged",
        omission="Mesh vertex arrays and non-physical display/schema attributes stay in repository registry/USD; all registered assets retain per-shape physical inputs, materials and mass properties here"))
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
        save("final_reader_and_actual_event_evidence.json", final_audit_evidence(audit))
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
        "protection保存原A座及历史命名空间保护检查；asset_summary为35个资产逐项保留尺寸、内腔、质量惯量、材质、28块碰撞输入参数。portable_sample只有已有独立便携episode的清单、正常读取及无损归档校验；约1.96GB数据本体不在精简包。\n\n"
        "10.70mm是最大已采样正的保守完整路径证书；10.72–11.00mm完整路径未知，11.02mm及以上仅在声明直立四方位和平移规则下入口排除。不能将10mm可完成反推为实物尺寸。\n\n"
        "成功必须实际释放、脱指撤离及3秒稳定；preview、开发成功但无冻结H5指纹、短接口诊断、预检/初始化/服务失败与进程中断不填20/20配额。自然失败和确定性动作偏差分组。\n\n"
        "受控失败正式准入还逐条核对实际teacher_events与配置/H5时刻、INSERT阶段和实际深度；仅配置声明不足。final_reader_and_actual_event_evidence仅在显式最终审计提供时生成，包含逐条实际事件、正常ACT/DP读取及whole-episode split；historical_closed_examples仍保留其原始局部数量，不代表最终配额。\n\n"
        "原生速度与差分仍可能有告警，静态完整烹饪网格/所有回退无法完全读取；逐块约14μm抽样差和原座约44.7nm射线面差不是全局界或真实精度。相机安装固定并记录实际参数；控制器使用器皿真值。\n\n"
        "collect/train/自动验证均standard，训练RNG种子单独配置；random10已取消。原12.5mm配套冲突结论与real_calibrated=false保留，原历史目录/阅读包不覆盖。\n", encoding="utf-8")
    (OUT / "复现与数据读取.md").write_text('''# 复现与数据读取

以下命令在工程根目录执行，仿真默认GUI；需要后台运行时显式加`--headless`。新输出目录必须不存在，单GPU顺序运行。

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher \\
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \\
 --output outputs/lab_cuvette_loading/Size_v1/NEW_SINGLE_RUN
```

冻结standard只接受10mm资产；直接增加`--asset-id cuvette_xy_1050`会被冻结守卫拒绝。其他注册尺寸使用独立未冻结的探索配置与新目录，重新检查几何及物理，不继承正式成功。原座保持不变。

现有探索配置的实际入口如下；快照configs/exploration保留同一配置模板。解析器会同步更新视觉/碰撞引用和质量属性，但不会自动改变原座或调整插入轴；不能由示例命令推断10.50mm成功：

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher \\
 --config config/lab_cuvette_loading/Size_v1/variant_evaluation_1030.yaml \\
 --asset-id cuvette_xy_1050 \\
 --output outputs/lab_cuvette_loading/Size_v1/NEW_VARIANT_1050 --headless
```

正式固定验证和采集：

```bash
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase success --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION \\
 --allow-after-verified-five --headless
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \\
 --phase controlled_failure --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION \\
 --allow-after-verified-five --headless
```

verify5必须新目录且5/5真实完整成功；后两阶段需显式审阅后放行。此后自然成功采集与受控失败可以交错，优先保留自然失败；不要求先满20条成功。可以先用`--phase controlled_failure --episodes-per-process 1 --max-processes 1 --allow-after-verified-five`完成1条真实任务的INSERT提前停，验证失败元数据及读取链路，再补其余数据。这条按实际提前停状态独立判分，不是缩短接口预算；若累计失败尚未满20，driver阶段退出2表示配额未满，实际单集结果另查独立评分。控制失败用固定INSERT停止深度1/5/10/18mm补充，记录完整偏差spec；只改动作，无场景随机化。各进程真实wait退出后才归档日志。非零仿真子进程退出（含143）保守单列，不能伪称exit0。

全部仿真进程闭合后才能运行目录审计，不能读取活动H5。以下审计本次正式collection；复现NEW_COLLECTION需相应替换根目录和索引目录。索引与FINAL_NEW_AUDIT路径必须尚不存在：

```bash
../labutopia-env/bin/python scripts/validate_lab_cuvette_size_v1_data.py \\
 outputs/lab_cuvette_loading/Size_v1/collection_standard \\
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \\
 --frozen-scene config/lab_cuvette_loading/Size_v1/frozen_scene.json \\
 --admission-scope official_collection \\
 --index outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset/episode_data.hdf5 \\
 --output-json docs/lab_cuvette_loading/Size_v1/data/FINAL_NEW_AUDIT/collection_audit.json
```

最终验证器自动核对actual official/closed/exit0进程证据，并逐条核对受控失败的实际teacher_events、配置、H5后继时刻/INSERT阶段/深度和终止结果；仅配置声明的偏差不能进入配额或索引。它同时正常ACT/DP读取成功/失败batch，并保存互斥whole-episode train/val ID，均为固定standard场景，不执行训练。

标准索引文件名固定为`collection_standard/dataset/episode_data.hdf5`。正常读取器接收dataset目录后固定追加`episode_data.hdf5`，不会自动发现名为`index.hdf5`的文件；请按上面的准确文件名创建。默认索引是同collection树内的相对H5外链，传输时必须移动整个collection树；原episode H5本身仍独立。`--copy-data`显式复制完整数据，需额外磁盘。ACT/DP任务配置默认准确指向上述collection_standard/dataset，复现新集合时必须显式调整dataset_path。训练成功BC默认success，失败用于单独分析，train/val按完整episode拆分、两者同一固定场景。

```bash
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \\
 outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset \\
 --sample-filter success --policy-type act
../labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py \\
 outputs/lab_cuvette_loading/Size_v1/collection_standard/dataset \\
 --sample-filter failure --policy-type dp --n-obs-steps 2
```

本轮不执行模型训练。训练入口的task配置为`lab_cuvette_size_v1_act`或`lab_cuvette_size_v1_dp`，启用冻结守卫，自动验证standard；training.seed只控制训练随机数，不允许开启场景随机化。

以下仅为未来明确启动训练时的正常入口示例，本轮未执行。ACT仅换task仍会继承旧相机名，必须精确覆盖`policy.camera_names=[side_camera_rgb,wrist_camera_rgb]`；DP从shape_meta/obs_encoder取两路相机，不加入不支持的camera_names字段。输出目录须不存在：

```bash
../labutopia-env/bin/python train.py --config-name=train_lab_cuvette_loading_act \\
 task=lab_cuvette_size_v1_act \\
 'policy.camera_names=[side_camera_rgb,wrist_camera_rgb]' \\
 hydra.run.dir=outputs/lab_cuvette_loading/Size_v1/FUTURE_TRAIN_ACT_NEW
../labutopia-env/bin/python train.py --config-name=train_lab_cuvette_loading_dp \\
 task=lab_cuvette_size_v1_dp \\
 hydra.run.dir=outputs/lab_cuvette_loading/Size_v1/FUTURE_TRAIN_DP_NEW
```

任一命令末尾加`--cfg job --resolve`只合成/打印Hydra配置并退出，不创建workspace、不读取H5或训练。实际CPU合成证据在future_training_hydra_compose_cpu_check.json。collect/train/自动验证均保持standard、场景随机化关闭；成功BC、相同冻结场景的whole-episode train/val划分不变。这里自动验证是离线验证损失，不能写成本轮已经执行policy物理闭环评估。

独立离线资产生成（新目录；不启GPU）：

```bash
bash demos/lab_cuvette_external/usd_python.sh \\
 -m demos.lab_cuvette_size_v1.build_assets --widths-mm 12.5 11.0 10.5 10.0 9.5 \\
 --directory assets/lab_cuvette_loading/Size_v1_REPRO_NEW
```

完整家族扫描会更新其工作副本的Size_v1注册表及元数据。须在新worktree/工程副本执行，不能回写正式冻结工作区；以下worktree/输出均需不存在，同级现有USD运行环境继续复用：

```bash
git worktree add --detach ../LabSim_Size_v1_GEOMETRY_REPRO_NEW HEAD
cd ../LabSim_Size_v1_GEOMETRY_REPRO_NEW
bash demos/lab_cuvette_external/usd_python.sh \\
 -m demos.lab_cuvette_size_v1.scan_family \\
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \\
 --output outputs/lab_cuvette_loading/Size_v1/NEW_GEOMETRY_SCAN \\
 --geometry-site /home/wujing/Desktop/vla/physicalrsi-runtime/sim-env/lib/python3.11/site-packages
```

返回原工程根目录再运行任务命令。几何环境路径为本机已核查的现有依赖位置，换机器时需指向其已有shapely/trimesh依赖，不能将绝对路径当作资产外链。正式便携episode已有独立导出及正常读取/无损归档校验，小证据在portable_sample；大数据不复制到本精简阅读包。
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
