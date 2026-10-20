#!/usr/bin/env python3
"""Build a short current-round DOCX/MD from actual Env_v1 evidence.

Run with the workspace-bundled Python after the documents skill's one-time
artifact marker. This program does not launch Isaac/models, modify experiments,
copy HDF5, render Word, or infer success from a controller phase.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ENV_REL = Path("outputs/lab_cuvette_loading/Env_v1")
DOC_REL = Path("docs/lab_cuvette_loading/Env_v1")
NON_PHYSICAL = {"GEOMETRY_PRECHECK_BLOCKED", "GEOMETRY_PREFLIGHT_BLOCKED",
                "GEOMETRY_BLOCKED", "PHYSICS_INVALID", "INITIALIZATION_INVALID",
                "INIT_INVALID", "PROCESS_INTERRUPTED", "INPUT_CONTRACT_ERROR",
                "MODEL_SERVICE_ERROR", "MODEL_ERROR", "PROCESS_ABORT"}


def lookup(value, dotted, default=None):
    for key in str(dotted).split("."):
        try:
            value = value[int(key)] if isinstance(value, list) else value[key]
        except (KeyError, TypeError, ValueError, IndexError):
            return default
    return value


def state(value):
    return "通过" if value is True else "未通过" if value is False else "未知"


def number(value, digits=2):
    return "未知" if value is None else f"{float(value):.{digits}f}"


def short(value, limit=44):
    text = str(value if value is not None else "未知")
    return text if len(text) <= limit else text[:limit-1] + "…"


class Evidence:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = {}
        self.warnings = []

    def path(self, value):
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def register(self, path):
        path = self.path(path).resolve()
        if not path.is_file():
            self.warnings.append(f"缺少文件 {path}")
            return None
        try:
            key = str(path.relative_to(self.root))
        except ValueError:
            key = str(path)
        # Large media/H5 are identified by size; do not hash checkpoints or H5.
        entry = {"path": key, "bytes": path.stat().st_size}
        if path.suffix.lower() not in {".h5", ".hdf5"}:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(2**20), b""):
                    digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
        self.sources[key] = entry
        return path

    def json(self, path, default=None):
        path = self.register(path)
        if path is None:
            return {} if default is None else default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            self.warnings.append(f"无法读取JSON {path}: {exc}")
            return {} if default is None else default

    def tail(self, path):
        path = self.path(path)
        if not path.exists():
            return {}
        # Full physics JSONL can be large; only a post-step terminal row is needed.
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size-1024*1024))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            try:
                return json.loads(line)
            except ValueError:
                continue
        return {}


def run_snapshot(e, directory, process_map):
    result_path = directory / "result.json"
    result = e.json(result_path)
    collector_path = directory / "episode_0000_result.json"
    collector = e.json(collector_path) if collector_path.exists() else {}
    events_path = directory / "teacher_events.json"
    events = e.json(events_path, []) if events_path.exists() else []
    terminal = e.tail(directory / "physics_records.jsonl")
    labels = collector.get("labels", {})
    run_name = directory.parent.name
    process = process_map.get(run_name)
    process_evidence = e.json(process) if isinstance(process, str) else {}
    exit_code = process_evidence.get("exit_code", process_evidence.get("process_exit_code"))
    media = []
    for filename in ("dual_view.mp4", "side_camera.mp4", "wrist_camera.mp4"):
        path = directory / filename
        if path.exists() and path.stat().st_size > 0:
            media.append(str(e.register(path).relative_to(e.root)))
    return {"run_name": run_name, "episode_directory": str(directory.relative_to(e.root)),
            "episode_id": result.get("episode_id"), "task_type": result.get("task_type"),
            "policy_id": result.get("policy_id"), "simulation_seconds": result.get("simulation_seconds"),
            "wall_seconds": result.get("wall_seconds"), "task_success": result.get("task_success"),
            "full_success": result.get("full_success"), "record_valid": labels.get("record_valid", result.get("record_valid")),
            "eligible_for_success_bc": labels.get("eligible_for_success_bc", result.get("eligible_for_success_bc")),
            "eligible_for_failure_analysis": labels.get("eligible_for_failure_analysis", result.get("eligible_for_failure_analysis")),
            "termination_reason": result.get("termination_reason"), "failure_type": result.get("failure_type"),
            "source_slot_cleared": result.get("source_slot_cleared"), "grasp_success": result.get("grasp_success"),
            "transport_success": result.get("transport_success"), "release_observed": result.get("release_observed"),
            "grasp_relative_pose": result.get("grasp_relative_pose", {}),
            "diagnostic_hold_window": result.get("diagnostic_hold_window", {}),
            "retreat_observed": result.get("retreat_observed"), "stable_after_retreat": result.get("stable_after_retreat"),
            "post_retreat_status": lookup(result, "post_retreat_window.status"),
            "phase": terminal.get("phase", events[-1].get("phase") if events else None),
            "terminal_tilt_deg": terminal.get("tilt_deg"),
            "physics_quality_flags": result.get("physics_quality_flags", []),
            "record_integrity_errors": collector.get("record_integrity_errors", result.get("record_integrity_errors", [])),
            "process_exit_code": exit_code, "process_evidence": process,
            "physical_steps": result.get("actual_physics_steps"), "control_steps": result.get("actual_control_steps"),
            "media": media, "score_source": str(result_path.relative_to(e.root))}


def policy_boundary(e, directory, backend):
    """Inspect persisted model-visible metadata, excluding audit-only full metadata.

    This checks the declared RGB/proprioception boundary, not task capability or
    a global proof that an arbitrary planner never obtained outside information.
    """
    if backend == "pi05":
        logs = sorted((e.root/ENV_REL/"policy_backends").glob("pi05_service_*/service/inference.jsonl"))
        observed = []
        for path in logs:
            e.register(path)
            for line in path.read_text().splitlines():
                try: row = json.loads(line)
                except ValueError: continue
                if row.get("actual_model_call") is True:
                    observed.append(dict(request_index=row.get("request_index"),
                        input_keys=sorted(row.get("inputs", {})), source=str(path.relative_to(e.root))))
        if not observed: return {"valid": None, "scope": "actual_model_server_input_keys", "reason": "未见真实模型输入记录"}
        valid = all(row["input_keys"] == ["main_images", "states", "wrist_images"] for row in observed)
        return {"valid": valid, "scope": "shared actual π0.5 server RGB and8D proprioceptive input schema; per-episode action linkage separately retained",
                "actual_server_inputs": observed, "reason": "真实模型输入键为RGB双视角和本体状态" if valid else "模型输入含声明外字段"}
    path = directory/"planner/rpent_states/states.json"
    if not path.exists(): return {"valid": None, "reason": "缺少实际工具观测边界记录"}
    states = e.json(path)
    source = e.register("policy_backends/lab_cuvette_env_v1/policy_adapters.py")
    direct, nested = None, None
    if source:
        for node in ast.parse(source.read_text()).body:
            if isinstance(node, ast.FunctionDef) and node.name == "sensor_meta":
                for assignment in node.body:
                    if isinstance(assignment, ast.Assign):
                        names = [t.id for t in assignment.targets if isinstance(t, ast.Name)]
                        if "direct" in names: direct = ast.literal_eval(assignment.value)
                        if "nested" in names: nested = ast.literal_eval(assignment.value)
    if direct is None or nested is None: return {"valid": None, "reason": "无法读取声明的传感器白名单"}
    extras = []
    steps = states.get("steps", [])
    for index, row in enumerate(steps):
        cameras = row.get("state", {}).get("camera_meta", {})
        for name, metadata in cameras.items():
            prefix = f"steps/{index}/state/camera_meta/{name}"
            extras.extend(prefix+"/"+key for key in metadata if key not in set(direct)|set(nested))
            for key, allowed in nested.items():
                if isinstance(metadata.get(key), dict):
                    extras.extend(prefix+"/"+key+"/"+subkey for subkey in metadata[key] if subkey not in allowed)
    valid = not extras if steps else None
    return {"valid": valid, "scope": "Persisted RPent model-visible tool state camera metadata checked against explicit direct/nested RGB-sensor whitelist",
            "state_count": len(steps), "forbidden_metadata_paths": extras,
            "source": str(path.relative_to(e.root)),
            "reason": "实际工具返回含renderer/debug/depth等声明外元数据" if extras else "实际工具返回元数据符合严格白名单" if steps else "没有实际状态"}


def collect(e, manifest):
    envroot = e.root / ENV_REL
    selected = set(manifest.get("run_names", []))
    selected_episodes = set(manifest.get("episode_directories", []))
    paths = sorted(envroot.glob("*/episode_*/result.json"), key=lambda p: p.stat().st_mtime)
    runs = [run_snapshot(e, p.parent, manifest.get("run_process_evidence", {})) for p in paths]
    for run in runs:
        run["selected_primary_evidence"] = ((not selected or run["run_name"] in selected)
            and (not selected_episodes or run["episode_directory"] in selected_episodes))
    attempts = []
    selected_policy_dirs = {str(e.path(p).resolve()) for p in manifest.get("policy_attempt_dirs", [])}
    # A selected primary trajectory must never hide earlier failed or tainted
    # attempts. Discover all actual attempt results, then label selection apart.
    policy_dirs = sorted({p.parent for p in (envroot / "policy_backends").rglob("result.json")}
                         | {Path(p) for p in selected_policy_dirs})
    for directory in policy_dirs:
        result = e.json(directory / "result.json")
        if result.get("backend") not in {"pi05", "astra", "harness"}:
            continue  # access probes and model-load checks are separate evidence
        request = e.json(directory / "request.json") if (directory / "request.json").exists() else {}
        actual_actions = int(result.get("executed_actions") or 0)
        # Never infer connectivity from prose, registry tests, or checkpoint load.
        integrated = result.get("integration_complete") is True and actual_actions > 0
        if result["backend"] == "pi05":
            integrated &= int(result.get("actual_model_requests") or 0) > 0
        if result["backend"] == "harness":
            integrated &= result.get("actual_vla_inference") is True
        boundary = policy_boundary(e, directory, result["backend"])
        primary = not selected_policy_dirs or str(directory.resolve()) in selected_policy_dirs
        result = dict(result, evidence_backed_integration=bool(integrated),
                      observation_boundary=boundary,
                      qualified_integration=bool(integrated and boundary.get("valid") is True and primary),
                      selected_primary_evidence=primary, request=request,
                      evidence_directory=str(directory.relative_to(e.root)))
        attempts.append(result)
    latest = e.json(envroot / "geometry_cache/latest.json")
    geometry_path = envroot / "geometry_cache" / latest.get("audit_relative_path", "missing.json")
    geometry = e.json(geometry_path)
    collision_rows = []
    collision_csv = geometry_path.parent / "collision_input_slices.csv"
    if collision_csv.exists():
        with e.register(collision_csv).open(encoding="utf-8") as stream:
            collision_rows = list(csv.DictReader(stream))
    checks = []
    for item in manifest.get("checks", []):
        evidence = e.json(item["evidence"])
        actual = lookup(evidence, item["json_key"])
        checks.append(dict(item, actual=actual, verified=actual == item.get("equals", True)))
    regressions = []
    for path in sorted(envroot.glob("minimal_pick_regression_*/summary.json")):
        regressions.append({"path": str(path.relative_to(e.root)), **e.json(path)})
    pi_load = e.json(DOC_REL / "policy_evidence/pi05_audited_actual_load_01.json")
    astra_access = e.json(DOC_REL / "policy_evidence/astra_actual_access_02.json")
    control_path = e.root/DOC_REL/"data/extract01_control_analysis.json"
    control_analysis = e.json(control_path) if control_path.exists() else {}
    auxiliary = {}
    preferred_renderer = DOC_REL/"data/preinsert_continuous_latch01_inspection/renderer_USD_sync_audit.json"
    if not e.path(preferred_renderer).exists():
        preferred_renderer = DOC_REL/"data/extract_fixed01_inspection/renderer_USD_sync_audit.json"
    for key, relative in {
        "renderer": manifest.get("renderer_audit", preferred_renderer),
        "historical_renderer_age": DOC_REL/"data/extract01_renderer_USD_dynamic_audit.json",
        "gui": DOC_REL/"data/extract_fixed01_GUI_validation.json",
        "live_api": DOC_REL/"policy_evidence/live_environment_api_validation.json",
        "control_comparison": DOC_REL/"data/extract_fixed01_control_comparison.json",
        "assets": DOC_REL/"current_asset_scene_manifest.json",
        "portable": DOC_REL/"data/preinsert01_portable_export_validation.json",
        "replay": DOC_REL/"data/replay_astra03_01_actual_summary.json",
        "reading_media": DOC_REL/"data/reading_media_provenance.json",
        "diagnostic_scope": DOC_REL/"data/preinsert_continuous_latch01_inspection/task_scope_filter_actual_check.json",
        "dataset_groups": manifest.get("dataset_group_evidence", DOC_REL/"data/dataset_group_validation.json"),
    }.items():
        if e.path(relative).exists(): auxiliary[key] = e.json(relative)
    figures = []
    for item in manifest.get("figures", []):
        path = e.register(item["path"])
        if path:
            figures.append(dict(item, path=str(path)))
    if not figures:
        # These are actual renders; their presence alone is not scene acceptance.
        for run in reversed(runs):
            image = e.path(run["episode_directory"]) / "side_camera_initial.png"
            if image.exists():
                figures.append({"path": str(e.register(image)), "role": "scene",
                                "caption": f"{run['run_name']} 实际侧视初帧 视野验收以运行记录为准"})
                break
        image = geometry_path.parent / "four_yaw_entrance_sections.png"
        if image.exists():
            figures.append({"path": str(e.register(image)), "role": "geometry",
                            "caption": "原座必要入口截面与器皿实际底部材料 四个直立方位"})
    media = []
    for item in manifest.get("media", []):
        path = e.register(item["path"])
        if path:
            media.append(dict(item, path=str(path)))
    if not media:
        for run in runs[-6:]:
            if run["media"]:
                media.append({"label": run["run_name"] + " 连续双视角", "path": str(e.path(run["media"][0]))})
    loading = [r for r in runs if r["task_type"] == "loading"]
    valid_failure = [r for r in loading if r["record_valid"] is True and r["task_success"] is False
                     and r["failure_type"] not in NON_PHYSICAL and r["eligible_for_failure_analysis"] is True]
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=e.root, text=True).strip()
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=e.root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=e.root, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        head, branch, dirty = "unknown", "unknown", None
    return {"created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "git": {"head": head, "branch": branch, "working_tree_modified": dirty},
            "runs": runs, "policy_attempts": attempts, "checks": checks, "geometry": geometry,
            "collision_input_slices": collision_rows,
            "geometry_path": str(geometry_path.relative_to(e.root)), "regressions": regressions,
            "pi05_load": pi_load, "astra_access": astra_access, "figures": figures, "media": media,
            "extract01_control_analysis": control_analysis,
            "auxiliary": auxiliary,
            "reproduction_commands": manifest.get("reproduction_commands", []),
            "counts": {"full_loading_success": sum(r["full_success"] is True and r["record_valid"] is True for r in loading),
                       "valid_loading_failure": len(valid_failure), "recorded_episodes": len(runs),
                       "teacher_diagnostic_success": sum(r["task_type"] != "loading" and r["task_success"] is True
                                                         and r["policy_id"] == "truth_teacher" for r in runs)},
            "source_files": list(e.sources.values()), "warnings": e.warnings}


def make_pages(d):
    runs, attempts, geometry = d["runs"], d["policy_attempts"], d["geometry"]
    primary = [r for r in runs if r.get("selected_primary_evidence")]
    teacher = [r for r in runs if r.get("policy_id") == "truth_teacher"]
    full = d["counts"]["full_loading_success"]
    aux = d.get("auxiliary", {})
    renderer = lookup(aux, "renderer.cameras.wrist_camera", {})
    live = aux.get("live_api", {})
    def image(role):
        return [("image", f) for f in d["figures"] if f.get("role") == role][:1]
    policies = []
    for backend, label in (("pi05", "π0.5"), ("harness", "Harness VLA"), ("astra", "GPT 6 Astra")):
        rows = [a for a in attempts if a["backend"] == backend]
        policies.append([label, f"接口{sum(a['evidence_backed_integration'] for a in rows)}/{len(rows)}  合格{sum(a['qualified_integration'] for a in rows)}/{len(rows)}",
                         str(sum(int(a.get("executed_actions") or 0) for a in rows))])
    lifted = [r for r in teacher if r["source_slot_cleared"] is True]
    transported = [r for r in teacher if r["transport_success"] is True]
    matrix = [
        ["场景", "实际加载并录像", "单仪器 完整6×6架 原A/B座"],
        ["渲染相机", f"当前匹配{renderer.get('same_observation_matches_current_USD_within_1e_8_m', '未知')}/{renderer.get('samples', '未知')}", "原projection与动态年龄问题分别修复验收"],
        ["原座几何", state(geometry.get("geometry_valid")), "刚性直立入口仍受阻"],
        ["提取与搬运", f"实际清槽{len(lifted)}条 搬运{len(transported)}条", "子任务整体保持按独立结果另判"],
        ["完整装载", f"成功{full}条", "未完成插入 松爪 撤离稳定"],
        ["真实环境API", f"{sum(c.get('passed') is True for c in live.get('checks', [])) if isinstance(live.get('checks'), list) else len(live.get('checks', {}))}项 实测{state(live.get('all_checks_passed'))}", "random仅初始化 非任务批次"],
        ["三策略", "真实有限短链接通", "各0.25秒动作 非任务级能力评测"],
        ["数据", f"完整成功{full} 有效失败{d['counts']['valid_loading_failure']}", "20+20及正式5/10未开始"],
    ]
    page1 = [("title", "LabSim Env v1 本轮实施与结果报告"),
             ("p", f"更新 {d['created_at']}。面向项目协作者，记录本轮新实现、真实运行和剩余关口。完整原座装载尚未完成；已完成的提取、搬运、诊断和接口功能分别验收。"),
             ("h", "当前完成矩阵"), ("table", (["项目", "实际状态", "范围"], matrix)),
             ("p", "保留旧资产和失败结果。任务成功、记录有效、几何可行及真实校准互相独立；诊断成功不进入完整loading成功BC。未训练模型，也不把软件渲染状态关联误差称为真实物理精度。"),
             ("p", f"分支 {d['git']['branch']}；HEAD {d['git']['head']}。生成时工作区存在变更 {d['git']['working_tree_modified']}，最终提交与包内版本清单核对。")]
    samples = renderer.get("samples")
    maximum = lookup(renderer, "position_residual_m.maximum")
    previous = lookup(aux, "historical_renderer_age.cameras.wrist_camera.position_residual_m.maximum")
    page2 = [("h", "场景关系和真实相机"),
             ("p", "参考视频的白色6×6架位于目标仪器开口一侧，盖板保持打开，仅保留一台目标仪器。机器人采用Franka代理；器皿横向12.5 mm和高度67.5 mm，架体和仪器尺度不随画面调整。布局仍是视频关系估计，未实物标定。")]
    page2 += image("reference") + image("scene")
    page2 += [("p", "固定side_camera与挂在panda_hand的WristCameraV1全程记录真实不同renderproduct。腕相机当前局部眼点[.075,0,0] m、目标[0,0,.35] m。先修复真实projection与读取K不一致，再单独核查动态renderer状态年龄。"),
              ("p", f"当前已验收样例：{renderer.get('same_observation_matches_current_USD_within_1e_8_m', '未知')}/{samples or '未知'}个腕相机观测对当前USD位置误差小于1e−8 m，最大{number(maximum, 16)} m。前一extract01最大{number(previous*1000 if previous is not None else None, 6)} mm仅作为历史保留，不再写成当前未解决项。"),
              ("p", f"实际GUI窗口mapped {state(aux.get('gui', {}).get('GUI_window_mapped'))}。这证明新版本实际GUI运行；软件渲染状态关联通过不等于真实光学校准。手/前臂局部遮挡仍需按实际图像判断，遮挡比例未知。")]
    seats = geometry.get("seats", []); probe = lookup(seats, "0.orientations.0", {})
    all_four = bool(seats) and all(s.get("no_upright_XY_domain_for_all_four_yaws") is True for s in seats)
    all_yaw = bool(seats) and all(lookup(s, "all_upright_yaw_interval_certificate.all_upright_yaws_excluded") is True for s in seats)
    depth = lookup(seats, "0.candidate_insertion_depth_m")
    page3 = [("h", "原座几何关口和资产依据"),
             ("p", f"当前目标 {geometry.get('selected_target_seat_id', '未知')}；A/B原座、源CAD及内伸件保留。12.5 mm为用户名义外宽，20 g质量仍是假设。原座12.6 mm仅代表部分中央截面，不能由名义50 µm单侧余量判定全深度可行。"),
             ("p", f"实际材料切片必要条件：座高{number(probe.get('probe_seat_z_mm'))} mm、器皿底上{number(probe.get('probe_vessel_z_mm'))} mm。A/B四个直立方位整个XY域为空 {state(all_four if seats else None)}，全直立yaw排除证书 {state(all_yaw if seats else None)}。结论不涵盖无依据斜插、未知可动或弹性结构。")]
    page3 += image("geometry")
    asset_dims = lookup(aux, "assets.dimensions", [])
    descriptions = []
    for asset, frame, label in [("instrument_body", "derived_instrument_local_m", "当前机身"), ("open_assembly", "source_normalized_m", "原source开盖整体"), ("open_assembly", "derived_instrument_local_m", "当前近90度开盖派生整体")]:
        row = next((x for x in asset_dims if x.get("asset") == asset and x.get("frame") == frame), None)
        if row:
            try: dimensions = json.loads(row["value"])
            except (ValueError, TypeError): dimensions = []
            descriptions.append(label+" "+"×".join(number(v, 3) for v in dimensions)+" mm")
    if descriptions: page3.append(("p", "尺寸分列："+"；".join(descriptions)+"。当前整机yaw90°、架体−90°；旧V04 manifest的135°/45°不作为当前layout。完整来源和哈希见current_asset_scene_manifest.json。"))
    page3 += [("p", f"候选终深度{number(depth*1000 if depth is not None else None)} mm来自源座中心射线，尚非实测正常承托深度。入口已冲突，不能随意缩短终深度制造成功；未删除凸起、扩大孔、缩小碰撞或放宽穿透判据。"),
              ("p", "审计读取源/派生USD、实例代理、单位和累计变换，使用实际截面材料与几何并集。碰撞输入外轮廓和内空腔误差分列；实际PhysX烹饪表示和回退仍未知。抽样距离不是严格全局上界。"),
              ("p", f"审计指纹 {lookup(geometry, 'binding.fingerprint', '未知')}。输入资产、装配、路径、控制和实现变化后重新绑定计算。")]
    selected_teacher = [r for r in primary if r.get("policy_id") == "truth_teacher"] or teacher[-5:]
    run_labels = {"grasp_hold_04": "静态夹持04", "extract_transport_01": "原始提取01",
                  "extract_fixed_orientation_01": "固定姿态01", "extract_continuous_latch_01": "连续锁存01",
                  "preinsert_continuous_latch_01": "安全预插入01"}
    phase_labels = {"GRASP": "夹持", "EXTRACT": "提取", "TRANSPORT_HOLD": "搬运后保持", "DIAGNOSTIC_HOLD": "诊断保持"}
    reason_labels = {"GRASP_HOLD_COMPLETE": "静持完成", "GRASP_SLIP": "提取滑移",
                     "EXTRACT_TRANSPORT_COMPLETE": "搬运完成，保持未过", "PREINSERT_DIAGNOSTIC_COMPLETE": "预插入诊断完成"}
    run_rows = [[run_labels.get(r["run_name"], r["run_name"]), number(r["simulation_seconds"])+" s", phase_labels.get(r["phase"], r["phase"]), reason_labels.get(r["termination_reason"], r["termination_reason"]), state(r["task_success"])] for r in selected_teacher[-5:]]
    page4 = [("h", "抓持 提取 搬运的实际结果"),
             ("table", (["运行", "仿真时长", "末阶段", "终止原因", "独立结果"], run_rows or [["无完整新结果", "未知", "未知", "未知", "未知"]])),
             ("p", "grasp04是架内承重的3秒静持，不是悬持。extract01静置阶段架支撑约0.501 N、指摩擦Z约−0.305 N，共同平衡0.196 N假设重量。微抬后原始反馈与固定姿态两版均滑移，主动旋转反馈不是唯一成因。")]
    comp = aux.get("control_comparison", {})
    if comp:
        page4.append(("p", f"固定姿态对照：EXTRACT前{lookup(comp, 'prefix.samples', '未知')}个样本的pose/q/TCP/速度/执行命令逐值相同 {state(lookup(comp, 'prefix.all_selected_physical_state_and_command_exact'))}；指接触仍有浮点量级差异，未改判分门槛。zero_delay渲染变化与物理前缀核查分开记录。"))
    continuous = [r for r in teacher if "continuous_latch" in r["run_name"]]
    for r in continuous[-2:]:
        position = lookup(r, "grasp_relative_pose.maximum_position_drift_m")
        angle = lookup(r, "grasp_relative_pose.maximum_orientation_drift_deg")
        drift = lookup(r, "diagnostic_hold_window.position_drift_m")
        page4.append(("p", f"{r['run_name']}：实际清槽{state(r['source_slot_cleared'])}、抓持{state(r['grasp_success'])}、搬运{state(r['transport_success'])}；最大相对漂移{number(position*1e6 if position is not None else None)} µm/{number(angle, 5)}°。独立整体结果{state(r['task_success'])}；保持窗口位置漂移{number(drift*1e6 if drift is not None else None)} µm。" + ("原始false结果保留，不能因阶段完成而改写。" if r["task_success"] is not True else "此true仅属于预插入诊断，full_success及native_pair_success仍为null。")))
    control_page = [("h", "接触锁存修复与控制回归")] + image("control")
    preinsert_pass = any(r['task_type'] == 'preinsert_diagnostic' and r['task_success'] is True for r in teacher)
    control_page.append(("p", "连续锁存保留首次闭合目标，避免freeze到latch突然再张开；8 N上限、摩擦、增益及既有判分不变。"
        + ("最新安全预插入诊断已独立通过：冻结TRANSPORT_HOLD目标并等待实际quiet，安全接近后上抬保持。它未插入、未张爪或实际撤离，不越过原座几何门控。" if preinsert_pass else "后续保持与安全预插入仅依据实际新结果，不提前宣布通过；不越过原座几何门控。")))
    control_page += [("p", "此前锁存交接使夹爪目标突然张开约0.485 mm。修复后，提取及搬运期间器皿相对夹爪的最大位置漂移约30.42 µm，未通过增加夹持力或摩擦补偿。TRANSPORT_HOLD另行冻结机械臂目标，等待实际静置后再接近原座。"),
                     ("p", "已实际复现原minimal_pick专家任务：518控制周期、8.633秒，抬升111.837 mm，双指夹持保持1秒，独立结果SUCCESS，进程退出码0。ACT与Diffusion原有成功读取接口通过。"),
                     ("p", "最新Env_v1 CPU契约检查共52项，51通过、1跳过；RPent RPC与策略适配另有14项通过。它们核查接口与判分逻辑，不能代替上述实际物理运行。精确运行ID、原始终止代码和全部尝试见actual_runs.csv及report_evidence.json。")]
    attempt_rows = [[Path(a['evidence_directory']).name.replace('_attempt_', ' '), str(a.get('executed_actions', 0)), state(a['evidence_backed_integration']), state(a['qualified_integration']), short(a.get('termination_reason'), 25)] for a in attempts]
    page5 = [("h", "三策略真实接入和环境API"), ("table", (["后端", "全尝试中的接口与合格数", "实际动作总数"], policies)),
             ("p", "三条最终合格链各执行5个0.05秒动作，共0.25秒、15个控制步，均以POLICY_BUDGET结束。它们是真实有限接入尝试，不是120秒完整装载能力评测；正式5+5及20+20批次未开始。"),
             ("table", (["全部尝试", "动作", "接口", "合格主证据", "终止"], attempt_rows)),
             ("p", "Astra01工具发现失败、0动作；Astra02虽执行5动作，但实际工具输出含renderer/debug/depth诊断，因此不作为合格RGB策略证据。Astra03净化后重跑。历史尝试、原标签和排除原因全部保留。Harness使用真实RPent/Astra和所选π0.5 primitive，没有专家整流程工具。"),
             ("p", f"真实环境API检查全部通过 {state(live.get('all_checks_passed'))}：23项、6次reset、seed/装配复现、2秒暂停、0.05秒=3控制周期、chunk、迟到拒绝及native预检0控制步。random仅检查初始化，不是任务批次。旧raw RPC getter曾返回全量debug元数据；新getter已做CPU及实际保存metadata输入的契约检查，尚未重启raw RPC实测。Astra03/Harness实际模型tool已独立净化。"),
             ("p", "RPC实际日志证明只读调用及模型等待不推进物理。π0.5原始7维LIBERO末端增量经有界转换，非旧8维关节位置；Astra直接模式无VLA。Astra内部HTTP请求数未知，planner消息条数不冒充请求数。")]
    page6 = [("h", "数据 复现和最少实物信息"),
             ("p", f"完整loading合格成功{full}条、有效失败{d['counts']['valid_loading_failure']}条。20+20、100+100扩量及正式固定5/random10未开始。诊断成功、几何阻塞、初始化无效、模型错误和中断不混入完整任务配额。无实际撤离时post_retreat_window=unavailable，稳定性为null。"),
             ("p", "新记录保留双视角RGB、原始/执行动作、双指effort、前后状态、时间、阶段、资产与独立结果。普通ACT/DP可按success/failure/all_valid读取；预览/诊断仅按真实资格进入all_valid。原格式H5便携导出保存字节和标签，不宣称LeRobot/OpenPI转换完成。完整H5另行提供，不放小阅读包。")]
    portable = aux.get("portable", {})
    if portable:
        total_bytes = sum(int(x.get("bytes", 0)) for x in portable.get("files", []))
        page6.append(("p", f"最新诊断便携导出共{total_bytes}字节，H5外部依赖{portable.get('HDF5_external_dependencies', '未知')}；原H5字节保存{state(portable.get('original_HDF5_bytes_preserved'))}，ACT/DP普通读取记录均在清单。诊断task_success=true仍不进入完整loading success/failure配额，只允许声明范围的all_valid读取。"))
    replay = aux.get("replay", {})
    if replay:
        page6.append(("p", f"main真实动作回放已执行{replay.get('executed_control_ticks', '未知')}个控制周期，执行命令逐行一致{state(replay.get('exact_executed_commands'))}，进程退出码{replay.get('actual_exit_code', '未知')}。独立判分仍false，不继承源结果；这只验证0.25秒短诊断动作回放，不宣称完整物理状态逐位复现或装载成功。"))
    reading_media = aux.get("reading_media", {}).get("files", [])
    if reading_media:
        whole = [item for item in reading_media if item.get("whole_run_preserved")]
        page6.append(("p", f"阅读版媒体{len(reading_media)}个，其中{len(whole)}个保留对应单次运行全程；整段H264阅读版保留原分辨率、fps与全部帧，腕近景按声明时间裁剪，原录像保存。82.65秒主录像为同一次连续安全预插入诊断，未拼接为完整loading；腕近景为另列时间范围的片段。来源/派生SHA与编码命令入证据清单。"))
    for check in d["checks"][:5]:page6.append(("p", f"附加实测 {check.get('label', check['json_key'])}：{state(check['verified'])}；值{short(check['actual'], 60)}。"))
    group = aux.get("dataset_groups", {})
    if group:page6.append(("p", "本轮分组读取、过滤和导出附加核查已保存到report_evidence.json的dataset_groups来源，按其中实际值判定，不据文件存在推断训练资格。"))
    reproduce_page = [("h", "复现命令和恢复装载所需信息"),
              ("code", "\n".join(d.get("reproduction_commands") or ["bash demos/lab_cuvette_env_v1/run.sh --mode preview --output NEW_PREVIEW_DIR", "bash demos/lab_cuvette_env_v1/run.sh --mode serve --config config/lab_cuvette_loading/Env_v1/preinsert.yaml --output NEW_RPC_DIR"])),
              ("p", "每次使用新目录。精确run配置、模型request、源SHA和数据证据在同包清单；完整CLI与读取/视频/导出/RPC/三后端说明见项目Env_v1首页。命令存在不表示相应新批次已执行。"),
              ("h", "恢复原座装载需要的信息"),
              ("p", "只集中补三项：入口内伸件是刚性、可动还是弹性结构，以及运动/刚度依据；器皿底角、入口截面和实际进入方向；正常承托位置与装载深度。不能仅凭外观认定弹片或删除该结构。源CAD和历史结果保持，real_calibrated=false。"),
              ("p", ("已取得独立通过的安全预插入诊断，下一步依据实物结构证据恢复完整原座装载。" if preinsert_pass else "下一步继续取得独立通过的保持与安全预插入诊断，并依据实物结构证据恢复完整原座装载；已完成的实际提取搬运单独记录。") + "三后端任务级批次在环境稳定后运行，本轮不训练模型。")]
    reproduce_page.append(("h", "同包录像"))
    for media in d["media"]:reproduce_page.append(("media", media))
    return [page1, page2, page3, page4, control_page, page5, page6, reproduce_page]


def write_markdown(pages, path, d):
    lines = []
    for blocks in pages:
        for kind, value in blocks:
            if kind in {"title", "h"}: lines += [("# " if kind == "title" else "## ") + value, ""]
            elif kind == "table":
                header, rows = value
                lines += ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"]*len(header)) + " |"]
                lines += ["| " + " | ".join(str(v).replace("|", "/") for v in row) + " |" for row in rows]
                lines.append("")
            elif kind == "image":
                target = str(Path(value["path"]).relative_to(path.parent.resolve())) if Path(value["path"]).is_relative_to(path.parent.resolve()) else value["path"]
                lines += [value["caption"], f"![{value['caption']}]({target})", ""]
            elif kind == "media":
                target = str(Path(value["path"]).relative_to(path.parent.resolve())) if Path(value["path"]).is_relative_to(path.parent.resolve()) else value["path"]
                lines += [f"[{value.get('label', Path(value['path']).name)}]({target})", ""]
            elif kind == "code": lines += ["```bash", value, "```", ""]
            else: lines += [value, ""]
    lines += ["## 本轮视频与证据入口", ""]
    for item in d["media"]:
        target = str(Path(item["path"]).relative_to(path.parent.resolve())) if Path(item["path"]).is_relative_to(path.parent.resolve()) else item["path"]
        lines += [f"- [{item.get('label', Path(item['path']).name)}]({target})"]
    lines += ["", "全部来源、SHA256、尝试记录及未核实项见 report_evidence.json。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_docx(pages, path):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from PIL import Image

    doc = Document()
    for style in doc.styles:
        for border in list(style.element.findall('.//' + qn('w:pBdr'))):
            border.getparent().remove(border)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
    section.left_margin, section.right_margin = Cm(2.0), Cm(2.0)
    for name, size in (("Normal", 10.2), ("Title", 20), ("Heading 1", 14), ("Caption", 9)):
        style = doc.styles[name]
        style.font.name = "Aptos"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Noto Sans CJK SC")
        style.paragraph_format.space_after = Pt(5)
        style.paragraph_format.line_spacing = 1.13
    doc.styles["Title"].paragraph_format.space_after = Pt(12)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(8)
    for index, blocks in enumerate(pages):
        if index: doc.add_page_break()
        for kind, value in blocks:
            if kind in {"title", "h"}:
                doc.add_paragraph(value, "Title" if kind == "title" else "Heading 1")
            elif kind == "table":
                header, rows = value
                table = doc.add_table(rows=1, cols=len(header))
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = False
                widths = ([4.2, 4.3, 8.0] if len(header) == 3 else [3.4, 1.5, 2.4, 7.4, 2.0])
                widths = [x * 16.8/sum(widths) for x in widths]
                for j, word in enumerate(header): table.rows[0].cells[j].text = word
                for row in rows:
                    cells = table.add_row().cells
                    for j, word in enumerate(row): cells[j].text = str(word)
                repeat = OxmlElement("w:tblHeader")
                table.rows[0]._tr.get_or_add_trPr().append(repeat)
                for row_index, row in enumerate(table.rows):
                    trpr = row._tr.get_or_add_trPr()
                    trpr.append(OxmlElement("w:cantSplit"))
                    for j, cell in enumerate(row.cells):
                        cell.width = Cm(widths[j])
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        tcpr = cell._tc.get_or_add_tcPr()
                        borders = OxmlElement("w:tcBorders")
                        for edge in ("top", "left", "bottom", "right"):
                            border = OxmlElement("w:"+edge)
                            for k, v in {"val": "single", "sz": "5", "color": "D9D9D9"}.items(): border.set(qn("w:"+k), v)
                            borders.append(border)
                        tcpr.append(borders)
                        margins = OxmlElement("w:tcMar")
                        for edge in ("top", "left", "bottom", "right"):
                            el = OxmlElement("w:"+edge);el.set(qn("w:w"), "85");el.set(qn("w:type"), "dxa");margins.append(el)
                        tcpr.append(margins)
                        if row_index == 0:
                            fill = OxmlElement("w:shd");fill.set(qn("w:fill"), "E6EDF3");tcpr.append(fill)
                        for paragraph in cell.paragraphs:
                            paragraph.paragraph_format.space_after = Pt(0)
                            paragraph.paragraph_format.line_spacing = 1.08
                            if j == len(header)-1 and len(header) == 5: paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            for run in paragraph.runs:
                                run.font.size = Pt(8.7)
                                if row_index == 0: run.bold = True
                doc.add_paragraph("").paragraph_format.space_after = Pt(0)
            elif kind == "image":
                with Image.open(value["path"]) as image: w, h = image.size
                height_cap = float(value.get("max_height_cm", 10.0 if value.get("role") == "control" else 6.2))
                width = min(float(value.get("max_width_cm", 16.0)), height_cap*w/h)
                paragraph = doc.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.keep_with_next = True
                paragraph.add_run().add_picture(value["path"], width=Cm(width))
                doc.add_paragraph(value["caption"], "Caption")
            elif kind == "code":
                paragraph = doc.add_paragraph(value)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs: run.font.name = "DejaVu Sans Mono";run.font.size = Pt(7.4)
            elif kind == "media":
                paragraph = doc.add_paragraph()
                link = OxmlElement("w:hyperlink")
                from docx.opc.constants import RELATIONSHIP_TYPE
                source = Path(value["path"])
                target = str(source.relative_to(path.parent.resolve())) if source.is_relative_to(path.parent.resolve()) else str(source)
                relation = paragraph.part.relate_to(target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
                link.set(qn("r:id"), relation)
                run = OxmlElement("w:r");text = OxmlElement("w:t")
                text.text = value.get("label", source.name)+"  "+source.name
                run.append(text);link.append(run);paragraph._p.append(link)
            else: doc.add_paragraph(value)
    doc.core_properties.title = "LabSim Env v1 本轮实施与结果报告"
    doc.core_properties.subject = "当前版本实际运行与未完成验收"
    doc.core_properties.author = "LabSim 项目"
    doc.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True, help="New report directory; never overwrite old report")
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--stem", default="LabSim_Env_v1_本轮进展报告")
    parser.add_argument("--copy-media", action="store_true", help="Copy only selected images/videos; never HDF5")
    args = parser.parse_args()
    if args.output.exists(): raise SystemExit("Report directory already exists; use a new output path")
    e = Evidence(args.root)
    manifest = e.json(args.evidence_manifest) if args.evidence_manifest else {}
    data = collect(e, manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.copy_media:
        media_dir = args.output / "media";media_dir.mkdir()
        for index, item in enumerate(data["figures"] + data["media"]):
            source = Path(item["path"])
            if source.suffix.lower() in {".h5", ".hdf5"}: raise ValueError("HDF5 cannot be copied into the reading report")
            destination = media_dir / f"{index:02d}_{source.name}"
            shutil.copy2(source, destination)
            item["path"] = str(destination.resolve())
    pages = make_pages(data)
    write_markdown(pages, args.output / (args.stem + ".md"), data)
    write_docx(pages, args.output / (args.stem + ".docx"))
    (args.output / "report_evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"docx": str(args.output / (args.stem + ".docx")), "pages_planned": len(pages),
                      "runs": len(data["runs"]), "policy_attempts": len(data["policy_attempts"]),
                      "warnings": data["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
