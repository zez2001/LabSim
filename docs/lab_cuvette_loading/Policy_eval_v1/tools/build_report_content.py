"""Build an eleven-section report source from actual frozen evaluation JSON.

Creates only new report_content.json and RESULTS.md. No DOCX authoring,
artifact marker, model/API call, trajectory relabeling or source mutation.
The companion build_report.py handles Word layout; root renders every page.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
LABELS = {"approach_grasp": "接近抓取区域", "grasp": "有效抓持", "extract": "完全离架",
          "held_transport_50mm": "持物横移50 mm", "transport": "固定预插入区域", "align": "对准",
          "insert": "有效插入到位", "support_transfer": "目标承托", "released": "实际脱指",
          "retreated": "实际撤离", "stable_complete": "连续稳定"}
GROUPS = {"gpt6": "GPT-6 direct P9", "pi05": "π0.5 LIBERO RPC"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def f(value, digits=3):
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def n(value):
    return "N/A" if value is None else str(int(value))


def para(text):
    return dict(type="paragraph", text=text)


def table(headers, rows, widths, **kwargs):
    return dict(type="table", headers=headers, rows=rows, widths_cm=widths, **kwargs)


def figure(name, caption, *, width=16.4, height=20):
    return dict(type="image", path="analysis:figures/" + name, caption=caption,
                width_cm=width, height_cap_cm=height)


def still(case, filename, caption, *, width=14.0):
    return dict(type="image", path=f"evidence:media/{case}/frames/{filename}", caption=caption,
                width_cm=width, height_cap_cm=6.5)


def junit(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    skipped = [case for case in cases if case.find("skipped") is not None]
    failed = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
    return dict(total=len(cases), skipped=len(skipped), failed=len(failed), passed=len(cases) - len(skipped) - len(failed),
                skip_reasons=[case.find("skipped").get("message") for case in skipped])


def markdown(content):
    lines = ["# " + content["title"], "", content["subtitle"], ""]
    for page in content["pages"]:
        lines += ["## " + page["title"], ""]
        for block in page["blocks"]:
            kind = block["type"]
            if kind == "paragraph":
                lines += [block["text"], ""]
            elif kind == "table":
                def cell(value):
                    if value is None:
                        return "N/A"
                    return str(value).replace("|", "\\|").replace("\n", "<br>")
                lines += ["| " + " | ".join(map(cell, block["headers"])) + " |",
                          "| " + " | ".join("---" for _ in block["headers"]) + " |"]
                lines += ["| " + " | ".join(map(cell, row)) + " |" for row in block["rows"]]
                lines += [""]
            elif kind == "image":
                name = Path(block["path"].split(":", 1)[1]).name
                lines += [f"![{block['caption']}](figures/{name})", ""]
            elif kind == "code":
                lines += ["```bash", block["text"], "```", ""]
    lines += ["## 证据与版本入口", "",
              "[冻结协议](../../../config/lab_cuvette_loading/Policy_eval_v1/protocol.json)、"
              "[GPT 身份](gpt_identity.json)、[π0.5 身份](pi05_identity.json)、"
              "[公开输入与原生动作](input_contracts.md)、[π0.5 processor 与执行](pi05_input_contract.md)。", "",
              "工程反馈包中的 summary.json、episodes.csv、stage_rates.csv、逐集闭合凭据及完整 Progress 可复算本报告。"
              "汇报包的 media/ 目录包含下文命名的四段连续视频。大型 H5 和真实模型输入留在工程端，身份及 SHA256 在表中给出。"
              "最终提交、远端与 CI、历史保护核验见反馈包 publication.json 和 protection_final.json；其结果在发布时生成，不提前标为已通过。", ""]
    return "\n".join(lines)


def create(root, evidence, analysis, protocol_path, output, markdown_output):
    if output.exists() or markdown_output.exists():
        raise FileExistsError("Use new report source and Markdown outputs; never overwrite a prior report")
    summary_path = analysis / "summary.json"
    summary = load(summary_path)
    protocol = load(protocol_path)
    metrics = evidence / "metrics_final_01"
    costs_summary = load(metrics / "costs_summary.json")
    initial = load(metrics / "initial_states.json")
    context = load(evidence / "validation/context_audit.json")
    readers = load(evidence / "validation/official_reader_summary.json")
    media = load(evidence / "media/final_media_manifest.json")
    gpt_identity = load(root / "docs/lab_cuvette_loading/Policy_eval_v1/gpt_identity.json")
    pi_identity = load(root / "docs/lab_cuvette_loading/Policy_eval_v1/pi05_identity.json")
    by_case = {row["trial_id"]: row for row in summary["episodes"] if row["started"]}
    case_order = ["gpt6_01", "pi05_01", "gpt6_02", "pi05_02"]
    if set(by_case) != set(case_order):
        raise ValueError("This report composition expects the actual two completed pairs; do not silently drop episodes")
    costs = {case: load(metrics / "costs" / f"{case}.json") for case in case_order}
    groups = summary["groups"]
    if not context["passed"] or not readers["passed"]:
        raise ValueError("Context or official reader audit has not passed")
    if summary["protocol_sha256"] != sha(protocol_path):
        raise ValueError("Analysis and frozen protocol identity differ")
    cpu = junit(evidence / "validation/repository_cpu_release.xml")
    focused = junit(evidence / "validation/evaluation_cpu_final.xml")
    diagnostics = sorted((evidence / "validation").glob("diagnostic_*_closed.json"))
    diagnostic_count = sum(load(path).get("passed") is True for path in diagnostics)
    formal_gpt_calls = sum(costs[c]["model_calls"] for c in case_order if c.startswith("gpt6"))
    formal_gpt_cost = sum(costs[c]["estimated_usd"] for c in case_order if c.startswith("gpt6"))
    total_spent = costs_summary["source_identity"]["ledger_estimated_usd"]
    budget_cap = protocol["budget"]["cap_estimated_usd"]
    diagnostic_cost = total_spent - protocol["budget"]["estimated_usd_before"] - formal_gpt_cost
    diagnostic_gpt_calls = costs_summary["source_identity"]["ledger_network_attempts"] - protocol["budget"]["network_attempts_before"] - formal_gpt_calls
    g1 = by_case["gpt6_01"]
    drift = next(row for row in g1["drift_intervals"]["operation"] if row["available"])
    media_by_case = {row["case_id"]: row for row in media["cases"]}
    token_records = []
    token_sources = []
    for case in ("pi05_01", "pi05_02"):
        path = evidence / f"formal_{case}/model/effective_input_audit.jsonl"
        token_sources.append(path)
        token_records += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    token_counts = set((r["raw_token_count"], r["model_max_tokens"], r["active_token_count"], r["truncated"]) for r in token_records)
    if token_counts != {(264, 200, 200, True)} or {r["task_text_sha256"] for r in token_records} != {pi_identity["task_text"]["task_text_sha256"]}:
        raise ValueError("Actual live token inputs differ; revise method report instead of using old token facts")
    p = []
    def page(title, blocks):
        p.append(dict(title=title, blocks=blocks))

    overview_rows = []
    for group_id in ("gpt6", "pi05"):
        group = groups[group_id]; interval = group["end_to_end_success"]
        overview_rows.append([GROUPS[group_id], f"{group['planned']} / {group['started']}",
            f"{group['environment_valid']} / {group['record_complete']}", f"{group['success']} / {group['started']}",
            f"{100 * interval['lower']:.3f}%–{100 * interval['upper']:.3f}%"])
    page("结论概览", [
        para("两套冻结方案均已真实执行，但本轮没有完成从来源架到腔内放稳的完整装载。GPT首集完成物理抓持、离架及持物横移，随后主动结束；第二集受原API费用预留限制截断。π0.5两集均未建立有效抓持，因手掌与仪器接触而安全终止。"),
        table(["执行方案", "计划 / 启动", "环境有效 / 记录完整", "完整成功", "95% Wilson区间"], overview_rows, [3.0, 2.6, 3.9, 2.3, 5.0]),
        para(f"每组仍有{groups['gpt6']['unstarted']}集未启动。按事先固定的成对规则，GPT02费用终止后完成π0.5配对集，再停止后续计划；未启动集没有进入分母。另有{diagnostic_count}条已闭合接口诊断，全部独立保存，不混入正式结果。"),
        para("端到端成功率分母包括全部已启动正式集；当前环境有效且任务可评估子集也各为2集，因此两种口径同为0/2。GPT02仍标记为预算截断；该记录说明当时未完成任务，不能推断若继续运行必然失败。成功完成时间样本n=0，结果为N/A。"),
        para("结果仅描述同一standard布局下两套当前执行方案。输入信息、原生工具与动作chunk不同，且样本量很小；当前证据不足以比较通用模型能力或估计跨场景成功概率。原资产、控制器、物理配置、reward、独立scorer与数据资格规则保持基线。")])

    env = protocol["environment"]
    page("任务场景与冻结环境", [
        para("任务链为来源架抓取、拔出、搬运、内部座对准与插入、支撑交接、松爪、实际脱指和撤离，并保持至少3秒稳定。原独立scorer裁定完整任务结果；Progress v1.2提供物理阶段、有效连续量及未完成原因。"),
        table(["项目", "实际冻结值及来源"], [
            ["版本与模式", f"{env['version']} / lab_cuvette_loading / {env['mode']}；场景及资产、光照、物理随机化关闭"],
            ["器皿与质量", f"{env['asset_id']}；{env['nominal_cuvette_mm'][0]}×{env['nominal_cuvette_mm'][1]}×{env['nominal_cuvette_mm'][2]} mm尺寸假设；{env['mass_kg'] * 1000:g} g工程质量"],
            ["来源和目标", f"完整6×6白色架{env['source_slot_id']}，远角F6蓝色器皿；单台开盖仪器内部A座 {env['target_seat_id']}"],
            ["目标深度", f"{env['target_depth_m'] * 1000:g} mm；原座几何保持不变"],
            ["频率与时间上限", f"物理{env['physics_hz']} Hz；控制{env['control_hz']} Hz；共同任务仿真上限{env['simulation_limit_s']:g} s"],
            ["相机", "侧视与腕视原生640×480 RGB；H5单独记录256×256 CHW；相机安装保持标准配置"],
            ["HF资产revision", env['asset_revision']],
            ["运行源码", env['runtime_commit']],
            ["共同场景指纹", context['common_evaluation_scene_fingerprint']]], [3.4, 13.4]),
        para("复用上一轮完整Teacher成功证明任务在相同物理配置下可执行，本轮未重复运行Teacher。上下文审计确认四集与Teacher的资产、布局、物理及执行参数一致；契约哈希差异来自truth_teacher与collect/eval记录用途，未发现其他配置差异。"),
        para("四集实际首次动作前的TCP、关节及器皿初态按保存值比较均一致，布局指纹相同；这些是当前仿真数值一致性记录，不是实物标定或真实精度证明。")])

    page("模型身份和实际输入动作", [
        table(["方法项", "GPT direct P9", "π0.5 RPC"], [
            ["实际模型", f"请求及返回gpt-6-astra；Cubence /v1/responses；显式P9配置，非旧默认P4", pi_identity['checkpoint']['name']],
            ["训练及身份范围", "供应商声明模型标识一致；中转后权重与训练数据未知；本轮无新训练", "本地LIBERO-130 fullshot SFT，权重SHA固定；本工程无LabSim微调，上游完整语料成员关系未知"],
            ["视觉", "两路640×480 JPEG质量60/high；固定侧图裁剪放大；最多一张历史腕图", "两路[1,480,640,3]uint8；processor保比例缩放补边至224，再float归一化到−1..1"],
            ["机器人状态", "q9/dq9、actual TCP、夹爪及公开接触；附robot-only FK/自身盒信息", "基座系TCP xyz+rotvec及左右指状态共8维；原q01/q99标准化后补零32维"],
            ["文本和上下文", f"reasoning={gpt_identity['parameters']['reasoning_effort']}；输出{gpt_identity['parameters']['max_output_tokens']}tokens；最近完整工具回执上下文；逐集清空", f"实际{len(token_records)}次processor输入均264→200tokens；完整核心任务前缀保留，静态TCP四元数尾部与净空提醒被截"],
            ["原生动作", "observe / move_ee / gripper / wait / finish；世界或TCP系m/rad通用工具；动作0.05–3s", "输出float32[1,5,7]；horizon10、执行chunk≤5；20Hz每行.05s"],
            ["动作执行", "连续IK、实际跟踪、接触锁存；模型自主选择动作与终止", "原LIBERO OSC反归一化后裁至[-1,1]，.05m/.5rad映射再限每轴.5mm/.004rad，夹爪±.008m，8N"],
            ["seed与等待", "策略seed未发送；每集新工具和空对话；推理时物理暂停", "每集新模型/adapter，Torch seed0；环境seed0另记；推理期间核对episode/step/time不变"]], [2.3, 7.25, 7.25], font_size_pt=8.7),
        para("器皿动态真值位姿、精确目标误差、Teacher waypoint、Progress与scorer没有自动送给两组策略。GPT比π0.5多了显式工具、公开触觉及机器人自身几何等信息；本轮比较冻结端到端方案，不将两者改造成统一动作策略。完整prompt、tool schema、checkpoint及归一化SHA见身份文件。")])

    result_rows = [[case, f(by_case[case]['simulation_seconds'], 3), n(by_case[case]['control_steps']),
                    LABELS.get(by_case[case]['farthest_stage'], "未确认抓取接近"),
                    by_case[case]['termination_reason'], "预算截断" if by_case[case]['censored'] else "正常评分"] for case in case_order]
    page("正式协议和逐集结果", [
        para(f"按GPT01→π01→GPT02→π02顺序运行，逐集独立reset且仅驻留一个Isaac任务。共同任务预算是{env['simulation_limit_s']:g}秒仿真；GPT每集最多{protocol['gpt6']['max_calls']}次逻辑调用、策略墙钟{protocol['gpt6']['episode_wall_s']}秒；π0.5最多{protocol['pi05']['max_model_requests']}次推理、{protocol['pi05']['max_actions']}动作。单请求及监督器保护另按协议固定，未人工接管或Teacher补全。"),
        table(["trial", "仿真s", "控制步", "最远物理达成", "原终止原因", "解释"], result_rows, [2.0, 1.5, 1.6, 3.3, 5.7, 2.7], font_size_pt=8.7),
        para("四条正式记录均闭合、环境有效、记录有效且task_success=false。主分母包含服务、预算和安全终止；本轮没有把系统终止移除以抬高成功率。有效任务子集未排除任何正式集；GPT02保留censored=true以便后续有足够预算时另作独立条件研究。"),
        table(["GPT01里程碑", "首次确认仿真时间s", "首次候选至确认等待s"], [
            [LABELS[key], f(g1['stage_results'][key]['first_confirmed_t'], 6), f(g1['stage_results'][key]['candidate_to_confirmation_wait_s'], 6)]
            for key in ('approach_grasp', 'grasp', 'extract', 'held_transport_50mm')], [5.5, 5.8, 5.5]),
        para("上表等待时长是候选证据持续到确认的等待，不是子任务执行总时长。未达成阶段时间保留not_reached/N/A，未将0秒放入均值。持物横移50mm由原scorer物理证据确认，与到达固定预插入区分开统计。")])

    achieved_interval = groups['gpt6']['stage_rates']['grasp']['achieved_per_started']
    missed_interval = groups['gpt6']['stage_rates']['transport']['achieved_per_started']
    page("阶段达成率与每集最远阶段", [
        figure("01_stage_rates.png", "阶段按物理历史首次确认统计；每组分母2，所有阶段unknown=0，控制端点证据覆盖率100%。", height=8),
        figure("02_episode_farthest_stage.png", "GPT01最远达到持物横移50mm；其余三集没有确认接近抓取阶段。", height=6),
        para(f"GPT组的接近、有效抓持、完全离架及持物横移均为{achieved_interval['successes']}/{achieved_interval['denominator']}；到达固定预插入区及之后全部为{missed_interval['successes']}/{missed_interval['denominator']}。π0.5各阶段为0/{groups['pi05']['started']}。已达成阶段比例的95% Wilson区间为{f(achieved_interval['lower']*100,3)}%–{f(achieved_interval['upper']*100,3)}%，未达成阶段为{f(missed_interval['lower']*100,3)}%–{f(missed_interval['upper']*100,3)}%，必须结合原始计数阅读。"),
        para("全部控制端点没有证据gap，因而此处not_reached是有覆盖证据下没有确认达成；unknown数量另行输出。阶段完成不推出完整任务成功，原独立评分仍要求支撑、脱指、撤离及3秒稳定。")])

    action_rows = []
    for case in case_order:
        c = costs[case]; a = c['actions']
        action_rows.append([case, n(c['returned_actions']), f"{a['accepted']}/{a['physical_receipts']}",
                            n(c['action_clipped']), n(a['partial']), n(a['execution_errors'])])
    collisions = [row for row in context['episodes'] if row['first_forbidden']]
    collision_rows = [[row['trial_id'], f(row['first_forbidden']['t'], 6), f(row['terminal_simulation_time_s'], 6),
                       str(row['forbidden_contact_event_count']), f(row['last_forbidden']['maximum_single_point_raw_force_norm_N'], 3)]
                      for row in collisions]
    page("终止原因和实际动作执行", [
        figure("03_termination_types.png", "GPT分别为主动提前结束和费用预算结束；π0.5两集均为原安全碰撞终止。", height=6),
        table(["trial", "返回动作数", "accepted/回执", "发生限幅动作", "部分执行", "执行异常"], action_rows, [2.1, 2.3, 3.7, 3.5, 2.5, 2.7], font_size_pt=8.7),
        para("accepted表示执行器接受请求，不是任务动作正确率。π0.5全部实际请求均有既有迁移限幅；这是冻结adapter的数值转换，不是新增补救。返回chunk尚未执行的尾部在安全终止后丢弃，未重放。π02最后一行仅执行两个控制周期，保留partial记录。"),
        table(["碰撞集", "首次接触s", "终止s", "原始事件数", "末事件单点力模N"], collision_rows, [2.3, 3.1, 2.8, 3.1, 3.5], font_size_pt=8.7),
        para("两次接触均定位为 /World/Franka/panda_hand/geometry/panda_hand 与 /World/Instrument/Collision/SourceMesh2。原callback冲量按当前physics_dt换算，表内是末事件最大单点原始向量模，不是器皿支撑净力，也未跨事件或接触点累加。碰撞属于策略/安全表现，未改标为环境无效。")])

    page("连续Progress轨迹与未完成要求", [
        figure("04_representative_progress.png", "四条真实正式轨迹的历史覆盖和有效插入进度；横轴为仿真秒。历史覆盖为诊断量，不是累计reward或完整成功率。", width=16.0, height=18),
        para("GPT01阶段覆盖在抓持和离架后上升，但固定预插入区未达成，Progress未完成原因为TRANSPORT_NOT_COMPLETED。有效插入进度始终为0；另外三集同样没有有效插入。分析消费完整progress_events.jsonl，包含GPT01结束时的attempt_ended finalize事件；其余三集尚未启动抓持尝试，事件数为0，逐步记录仍完整。"),
        para("GPT01只有1次抓持尝试，0次重试；其他集为0次尝试、0次重试。完整便携HTML保留全部原始控制端点、有效门控、单独单位曲线及真实视频时间映射，便于进一步核查。")])

    g1_media = media_by_case['gpt6_01']
    g1_grasp = next(row for row in g1_media['screenshots'] if '_grasp.png' in row['path'])
    g1_terminal = next(row for row in g1_media['screenshots'] if '_terminal.png' in row['path'])
    pi_terminal = next(row for row in media_by_case['pi05_01']['screenshots'] if '_terminal.png' in row['path'])
    page("真实双视角代表画面", [
        still('gpt6_01', Path(g1_grasp['path']).name, f"GPT01 实际抓持帧，t={f(g1_grasp['simulation_time_s'],6)}s；episode {g1['episode_id']}。"),
        still('gpt6_01', Path(g1_terminal['path']).name, f"GPT01 结束时仍夹持器皿，未放入目标；t={f(g1_terminal['simulation_time_s'],6)}s。"),
        still('pi05_01', Path(pi_terminal['path']).name, f"π01 安全停止帧，t={f(pi_terminal['simulation_time_s'],6)}s；episode {by_case['pi05_01']['episode_id']}。"),
        para("选择规则为展示唯一达成抓持/搬运的GPT01与π01典型安全终止，未仅挑选最佳终态。GPT02费用截断和π02重复碰撞的完整视频同样提供；四集均进入主表。截图按原video_timestamps最近真实帧选取，没有生成或插值运动。")])

    drift_rows = [["GPT01 全操作", f(drift['maximum_relative_translation_m'] * 1000, 6), f(drift['maximum_relative_rotation_rad'], 9),
                   n(drift['sample_count']), f(drift['observed_sampling_frequency_hz'], 0)],
                  ["GPT01 首次目标承托前", f(drift['maximum_relative_translation_m'] * 1000, 6), f(drift['maximum_relative_rotation_rad'], 9), n(drift['sample_count']), f(drift['observed_sampling_frequency_hz'], 0)],
                  ["所有集支撑交接", None, None, None, None], ["其他三集抓持漂移", None, None, None, None]]
    approach_rows = [[case, f(by_case[case]['continuous']['minimum']['grasp_approach_position_error_m']['value'] * 1000, 3),
                      n(by_case[case]['continuous']['target_operation_region_sample_count']),
                      f(by_case[case]['continuous']['maximum']['valid_insertion_progress']['value'], 3), "N/A"] for case in case_order]
    page("适用区间内的精细量和抓持漂移", [
        figure("05_applicable_target_metrics.png", "进入目标操作区的适用样本数为0；目标横向/姿态误差、有效深度及释放后稳定保持N/A，不把未达目标误写为0mm。", width=13.4, height=10.0),
        table(["区间", "相对平移mm", "相对转角rad", "样本数", "Hz"], drift_rows, [5.6, 3.1, 3.6, 2.6, 1.9], font_size_pt=8.7),
        table(["trial", "最近接近诊断mm", "目标区样本", "最大有效进度", "有效深度"], approach_rows, [2.1, 4.8, 3.2, 3.7, 3.0], font_size_pt=8.5),
        para(f"最近距离为实际TCP到当前器皿位姿变换后的配置抓取参考点的最小距离。原core在held=true时也确认approach阶段，该规则不改变距离数值；GPT01的{f(g1['continuous']['minimum']['grasp_approach_position_error_m']['value']*1000,3)}mm不能解释为固定来源抓取点误差或机器人精度。漂移以实际杯在手坐标的固定参考计算，包含杠杆臂转动，未按抓持质量过滤。GPT01无目标承托，故全操作与承托前区间相同；独立原物理记录复算已通过。上述微小漂移是当前仿真相对运动，不是真实器皿或平台精度。")])

    time_rows = []
    for case in case_order:
        e = by_case[case]; c = costs[case]
        time_rows.append([case, n(c['model_calls']), f(c['inference_seconds'], 3), f(e['resource']['latency_per_call_s']['mean'], 3),
                          f(c['wall_seconds'], 3), f(c['estimated_usd'], 6)])
    page("推理延迟墙钟与费用", [
        figure("06_latency_and_wall_time.png", "逐集先汇总再等权比较；GPT是HTTP端到端请求耗时，π0.5是adapter RPC predict，模型forward另行记录。", height=7),
        table(["trial", "模型调用", "推理合计s", "每调用均值s", "整集墙钟s", "估算USD"], time_rows, [2.1, 2.4, 3.0, 3.1, 3.1, 3.1], font_size_pt=8.7),
        para(f"正式GPT共{formal_gpt_calls}次实际网络调用，返回输入/输出token合计{sum(costs[c]['input_tokens'] for c in ('gpt6_01','gpt6_02'))}/{sum(costs[c]['output_tokens'] for c in ('gpt6_01','gpt6_02'))}，估算USD{f(formal_gpt_cost,6)}；另{diagnostic_gpt_calls}次诊断GPT调用估算USD{f(diagnostic_cost,6)}。账本累计{costs_summary['source_identity']['ledger_network_attempts']}次、USD{f(total_spent,6)}，原上限USD{f(budget_cap,2)}，剩USD{f(budget_cap-total_spent,6)}。余额不足下一请求的保守预留，触发原预算保护；未提高额度或重建账本。"),
        para(f"π0.5本地模型两集forward合计分别{f(costs['pi05_01']['model_forward_seconds'],3)}和{f(costs['pi05_02']['model_forward_seconds'],3)}秒；模型进程Torch峰值allocated均为{costs['pi05_01']['model_gpu_peak_allocated_bytes']:,} bytes，非整GPU/Isaac总显存。电力及本地运行费用未测量，费用为N/A。"),
        para("墙钟包含环境/模型启动、reset、推理、动作、记录导出和退出。推理与网络等待期间物理暂停，仿真时间不含推理等待。服务队列等待不能独立分离，保留N/A；本地usage×费率是费用估算，供应商真实账单和账户倍率未知。两组任务均未成功，不能用较短终止墙钟宣称完成任务更高效。")])

    h5_rows = []
    for case in case_order:
        e = by_case[case]
        original_h5 = next(row for row in e['source_files'] if row.get('kind') == 'original_h5_read_only')
        h5_rows.append([case + "\nmedia/" + case + "_dual.mp4", e['episode_id'], original_h5['sha256']])
    page("完整性复现与后续研究", [
        para(f"四集原H5、动作后继邻接、时间戳、闭合标记、完整Progress、原始视频解码均通过独立核验。当前CPU仓库检查{cpu['passed']}passed/{cpu['skipped']}skipped；跳过为现CPU解释器缺少4项RPent与1项pxr依赖，相关真实模型/Isaac链路已在各自隔离环境运行。评测专项检查{focused['passed']}passed。"),
        para("四集由正常发布版ACT及DP failure读取入口全部读出实际finite batch：ACT图像[3,3,256,256]，DP图像[3,3,3,256,256]，动作均[3,16,8]。H5及原标签前后哈希一致；成功BC资格全为false，没有生成训练样本冒充成功，也未执行训练。"),
        table(["trial及汇报包视频", "完整episode_id", "原H5 SHA256"], h5_rows, [4.1, 5.5, 7.2], font_size_pt=8.2),
        para(f"实际策略/仿真源码{env['runtime_commit']}；分析源码{summary['analysis_implementation']['code_commit']}。报告生成与最终发布另由publication.json及SHA清单绑定，测试后的文档/包装变更单列。原始大型H5定位为工程outputs/lab_cuvette_loading/Policy_eval_v1/20261103/formal_{{trial}}/environment/episode_0000/dataset/episode_0000.h5。"),
        dict(type="code", text='"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.analysis /absolute/path/to/metrics_final_01/trials.json --output /absolute/path/to/new_analysis\n"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.plots /absolute/path/to/new_analysis/summary.json --manifest /absolute/path/to/metrics_final_01/trials.json --output /absolute/path/to/new_figures'),
        para("当前关键结果是GPT可以建立一次物理抓持并离架搬运，原LIBERO π0.5迁移方案在此任务中提前碰撞，两组均未展示腔内装载能力。后续研究应先独立声明更充足预算、输入与动作迁移研究条件，再比较可达性/整手避障、目标区视觉对准和完整卸载行为。当前结果不支持通用模型排名、真实精度认证或跨布局成功率结论。")])

    sources = [summary_path, protocol_path, metrics / 'costs_summary.json', metrics / 'initial_states.json',
               evidence / 'validation/context_audit.json', evidence / 'validation/official_reader_summary.json',
               evidence / 'validation/repository_cpu_release.xml', evidence / 'validation/evaluation_cpu_final.xml',
               evidence / 'validation/gpt6_01_independent_drift.json', evidence / 'media/final_media_manifest.json',
               root / 'docs/lab_cuvette_loading/Policy_eval_v1/gpt_identity.json',
               root / 'docs/lab_cuvette_loading/Policy_eval_v1/pi05_identity.json', Path(__file__).resolve(),
               root / 'docs/lab_cuvette_loading/Policy_eval_v1/tools/build_report.py',
               *token_sources, *(metrics / 'costs' / f'{case}.json' for case in case_order), *diagnostics]
    source_records = [dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path)) for path in sources]
    content = dict(schema='labsim.Policy_eval_v1.report_content.v1', title='LabSim 器皿装载策略量化评测',
        subtitle='GPT 6 Astra direct P9 与 RLinf Pi05 LIBERO 冻结方案  固定standard场景  2026年11月3日',
        header='LabSim Policy_eval_v1  器皿装载冻结策略评测', author='LabSim 项目组',
        metadata_lines=['对象  Project_release_v1 standard  Progress v1.2',
                        f"正式规模  GPT与π各{groups['gpt6']['started']}集启动  各{groups['gpt6']['unstarted']}集因预算未启动"],
        pages=p, sources=['analysis:summary.json','evidence:metrics_final_01/costs_summary.json',
                         'evidence:validation/context_audit.json','evidence:validation/official_reader_summary.json',
                         'evidence:media/final_media_manifest.json'],
        provenance=dict(created_utc=datetime.now(timezone.utc).isoformat(), source_files=source_records,
            actual_runtime_commit=env['runtime_commit'], analysis_implementation=summary['analysis_implementation'],
            all_numeric_tables_programmatically_derived=True, source_episodes_modified=False,
            source_code_sha256=sha(Path(__file__).resolve()), rendered_document_created=False))
    assert len(p) == 11
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as destination:
        json.dump(content, destination, ensure_ascii=False, indent=2, allow_nan=False); destination.write('\n')
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    with markdown_output.open('x', encoding='utf-8') as destination:
        destination.write(markdown(content))
    return dict(content=str(output), markdown=str(markdown_output), pages=len(p), source_files=len(source_records),
                content_sha256=sha(output), markdown_sha256=sha(markdown_output), docx_authoring=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--analysis-dir', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New report_content.json')
    parser.add_argument('--markdown-output', type=Path, required=True, help='New RESULTS.md')
    args = parser.parse_args(argv)
    value = create(args.root.resolve(), args.evidence_root.resolve(), args.analysis_dir.resolve(),
                   args.protocol.resolve(), args.output.resolve(), args.markdown_output.resolve())
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
