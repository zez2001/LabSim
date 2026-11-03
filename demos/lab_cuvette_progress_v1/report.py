"""Portable scalar-only Progress v1.2 reports with genuine sample/video clocks.

The cursor always reads an original control endpoint, never an interpolated or
plot-thinned value. Display curves alone may be thinned, retaining extrema and
unknown/event boundaries. No source trajectory or previous report is modified.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil

from .io import iter_json_rows

REPORT_VERSION = 'Progress_v1.2.portable.v1'
STAGES = ('approach_grasp', 'grasp', 'extract', 'transport', 'align', 'insert',
          'support_transfer', 'release_retreat', 'stable_complete')
PLOT_METRICS = ('target_lateral_error_m', 'target_tilt_rad', 'target_yaw_error_rad',
    'raw_depth_m', 'raw_axial_depth_m', 'raw_depth_fraction', 'valid_insertion_progress',
    'target_depth_m', 'grasp_relative_translation_m', 'grasp_relative_rotation_rad',
    'target_bottom_support_N', 'target_bottom_gap_m', 'gripper_object_clearance_m',
    'stable_duration_s', 'gripper_opening_m', 'tcp_object_distance_m',
    'both_fingers_open_and_detached', 'stable_position_drift_m',
    'stable_orientation_change_rad', 'source_bottom_envelope_clearance_m',
    'preinsert_distance_m', 'grasp_approach_position_error_m',
    'grasp_approach_orientation_error_rad', 'approach_position_quality',
    'approach_orientation_quality')
STATUS_NAMES = ('active', 'completed_followed', 'temporarily_unmet',
                'evidenced_failure', 'evidence_missing', 'not_started', 'unknown')


def _scalar(value):
    if isinstance(value, bool):
        return int(value)
    return value if isinstance(value, (float, int)) and math.isfinite(value) else None


def _state_row(state, t_obs=None):
    metrics, missing = {}, {}
    source = state.get('metrics', {})
    for key in PLOT_METRICS:
        metric = source.get(key, {})
        # The original raw depth alias is a diagnostic value, not insertion
        # progress. Old records have no effective progress and remain unknown.
        if key == 'raw_axial_depth_m' and not metric:
            metric = source.get('raw_depth_m', {})
        value = metric.get('value') if metric.get('available') else None
        if key in ('valid_insertion_progress', 'raw_depth_fraction') and not metric:
            value = state.get(key)
        metrics[key] = _scalar(value)
        if metrics[key] is None:
            missing[key] = metric.get('reason') or 'metric_not_recorded'
    stages = state.get('stages', {})
    gates = state.get('insertion_gate_details') or {}
    applicable_metric = source.get('insertion_progress_applicable', {})
    applicable = state.get('insertion_progress_applicable', applicable_metric.get('value'))
    return dict(t=state.get('t'), t_obs=state.get('t') if t_obs is None else t_obs,
        stage=state.get('current_stage'), highest_stage=state.get('highest_ever_stage'),
        vector=state.get('stage_vector', []), continuous=state.get('current_stage_continuous'),
        metrics=metrics, missing=missing, hold_state=state.get('hold_state', 'unknown'),
        attempt_id=state.get('attempt_id'), coverage=state.get('coverage_progress'),
        hold_state_user=state.get('hold_state_user', state.get('hold_state', 'unknown')),
        insertion_progress_applicable=applicable,
        gate_reasons=dict(not_applicable=gates.get('not_applicable_reasons', []),
                          unknown=gates.get('unknown_reasons', [])),
        statuses=[stages.get(s, {}).get('user_status', 'unknown') for s in STAGES],
        status_reasons=[stages.get(s, {}).get('user_status_reason') for s in STAGES],
        effective=[stages.get(s, {}).get('effective_continuous') for s in STAGES])


def _plot_rows(rows, events, limit=2000):
    """Display-only reduction retaining extrema and all semantic boundaries.

    Mandatory boundaries can exceed ``limit``; evidence is never dropped just
    to satisfy a display budget. Full control endpoints are embedded separately.
    """
    if len(rows) <= limit:
        return rows
    import bisect
    mandatory = {0, len(rows) - 1}
    for i in range(1, len(rows)):
        before, after = rows[i - 1], rows[i]
        if ((before['stage'], before['hold_state'], before['vector']) !=
                (after['stage'], after['hold_state'], after['vector']) or
                any((before['metrics'].get(k) is None) !=
                    (after['metrics'].get(k) is None) for k in PLOT_METRICS)):
            mandatory.update((i - 1, i))
    times = [r['t'] for r in rows]
    for event in events:
        for field in ('t', 'candidate_start_t', 'confirmed_t'):
            t = event.get(field)
            if t is not None:
                index = min(len(rows) - 1, bisect.bisect_left(times, t))
                mandatory.update((max(0, index - 1), index))
    selected = set(mandatory)
    budget = max(0, limit - len(selected))
    buckets = max(1, budget // (2 * len(PLOT_METRICS) + 2))
    for bucket in range(buckets):
        start, end = bucket * len(rows) // buckets, (bucket + 1) * len(rows) // buckets
        selected.update((start, end - 1))
        for key in PLOT_METRICS:
            valid = [(rows[i]['metrics'].get(key), i) for i in range(start, end)
                     if isinstance(rows[i]['metrics'].get(key), (float, int))]
            if valid:
                selected.update((min(valid)[1], max(valid)[1]))
    return [rows[i] for i in sorted(selected)]


def _pack_rows(rows):
    """Compact scalar arrays, with repeated reasons interned rather than copied."""
    strings, lookup = [], {}
    def intern(value):
        if value is None:
            return None
        value = str(value)
        if value not in lookup:
            lookup[value] = len(strings)
            strings.append(value)
        return lookup[value]
    packed = []
    for row in rows:
        packed.append([row['t'], row['t_obs'], row['stage'], row['highest_stage'],
            row['hold_state'], row['attempt_id'], row['continuous'], row['coverage'],
            row['insertion_progress_applicable'], row['vector'],
            [STATUS_NAMES.index(s) if s in STATUS_NAMES else len(STATUS_NAMES)-1 for s in row['statuses']],
            [row['metrics'].get(k) for k in PLOT_METRICS],
            [[i, intern(row['missing'][k])] for i, k in enumerate(PLOT_METRICS) if k in row['missing']],
            [intern(s) for s in row['status_reasons']], row['effective'],
            [[intern(s) for s in row['gate_reasons']['not_applicable']],
             [intern(s) for s in row['gate_reasons']['unknown']]], row['hold_state_user']])
    return packed, strings


def _event_row(event):
    evidence = event.get('evidence') or {}
    return {**{k: event.get(k) for k in ('event_id', 'name', 't', 'attempt_id',
        'candidate_start_t', 'confirmed_t')}, 'reason': evidence.get('reason'),
        'outcome': evidence.get('outcome'), 'previous_outcome': evidence.get('previous_outcome')}


def _original_result_summary(original):
    """Embed outcome scalars only; complete original reports remain sidecars."""
    if not isinstance(original, dict):
        return {}
    source = original.get('result', original.get('independent_score', original))
    if not isinstance(source, dict):
        source = original
    keys = ('task_success', 'full_success', 'workflow_success', 'record_valid',
        'success_bc_eligible', 'eligible_for_success_bc', 'record_integrity_valid',
        'failure_type', 'termination_reason', 'failure_domain', 'record_purpose',
        'asset_id', 'scene_version', 'scorer_version', 'real_calibrated',
        'physics_quality_flags')
    return {key: source[key] for key in keys if key in source}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def generate_report(progress_directory, episode_directory=None, *, copy_videos=False):
    progress = Path(progress_directory).resolve()
    summary = json.loads((progress / 'progress_summary.json').read_text())
    config_path = progress / 'progress_config.resolved.json'
    config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    if episode_directory is None:
        episode_directory = summary.get('metadata', {}).get('source_trajectory', {}).get('episode_directory')
    episode = Path(episode_directory).resolve() if episode_directory else None
    rows = []
    for row in iter_json_rows(progress / 'progress_v1.jsonl.gz'):
        rows.append(_state_row(dict(row.get('after') or {}, t=row['t_next']), row['t_obs']))
    events = list(iter_json_rows(progress / 'progress_events.jsonl'))
    reduced = _plot_rows(rows, events)
    row_indices = {id(row): i for i, row in enumerate(rows)}
    packed, strings = _pack_rows(rows)
    videos, timestamps = [], {}
    if episode is not None:
        timestamp_path = episode / 'video_timestamps.json'
        if timestamp_path.is_file():
            timestamps = json.loads(timestamp_path.read_text())
        for name in ('side_camera.mp4', 'wrist_camera.mp4'):
            path = episode / name
            if path.is_file():
                original_hash = _sha256(path)
                if copy_videos:
                    destination = progress / 'media' / name
                    destination.parent.mkdir(exist_ok=True)
                    if destination.exists():
                        raise FileExistsError(destination)
                    shutil.copy2(path, destination)
                    path = destination
                videos.append(dict(name=name, src=os.path.relpath(path, progress),
                    original_sha256=original_hash, original_bytes=path.stat().st_size))
    metadata = summary.get('metadata', {})
    original = summary.get('original_result') or metadata.get('source_trajectory', {}).get('original_labels', {})
    data = dict(report_version=REPORT_VERSION, rows=packed, metric_keys=PLOT_METRICS,
        strings=strings, status_names=STATUS_NAMES,
        plot_indices=[row_indices[id(row)] for row in reduced],
        events=[_event_row(e) for e in events], videos=videos, timestamps=timestamps,
        display_sampling=dict(original_transitions=len(rows), displayed_rows=len(reduced),
            cursor_rows=len(rows), cursor_method='Original control endpoint at or before requested simulation time; no interpolation',
            method='Curves only: per-metric bucket extrema, all event, stage/hold and unknown boundaries'),
        reset_snapshot=_state_row(summary['reset_snapshot']) if summary.get('reset_snapshot') else None,
        first_control_observation=_state_row(summary['first_control_observation']) if summary.get('first_control_observation') else None,
        summary={key: summary.get(key) for key in ('progress_complete', 'termination_domain',
            'unfinished_requirement', 'failure_observation', 'attempts', 'milestones',
            'output_integrity', 'recording', 'config_sha256', 'progress_schema_version',
            'progress_evaluator_version', 'parameters_version')},
        original_result=_original_result_summary(original), thresholds=config.get('thresholds', {}),
        identity=metadata.get('source_trajectory', {}), evidence=metadata.get('input_evidence', {}))
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    target = progress / 'progress_report.html'
    target.write_text(_HTML.replace('__PROGRESS_DATA__', payload), encoding='utf-8')
    return target


_HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LabSim · Progress v1.2</title>
<style>
:root{color-scheme:light;--ink:#14252d;--muted:#61737b;--green:#167d62;--line:#dbe5e5;--bg:#f1f5f4}*{box-sizing:border-box}body{font:14px/1.5 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--ink)}main{max-width:1500px;margin:auto;padding:26px}h1{font-size:26px;margin:0}h2{font-size:17px;margin:0 0 10px}p{margin:8px 0}.muted{color:var(--muted)}.card{background:white;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid .card{margin:0}.videos{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:240px}video{width:100%;background:#10191c;border-radius:8px}figcaption{color:var(--muted)}input[type=range]{width:100%;accent-color:var(--green)}.facts,.tools{display:flex;gap:9px;flex-wrap:wrap}.fact{padding:8px 12px;border-radius:7px;background:#edf3f1}.stagegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stage{border:1px solid var(--line);padding:10px;border-radius:8px}.stage b{display:block}.yes{color:var(--green)}.no{color:#995e26}.unknown{color:#79838b}.failure{color:#b23636}button,input[type=number]{border:1px solid #bdcfca;background:#f6faf8;border-radius:7px;padding:6px 10px;font:inherit}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}input[type=number]{width:115px}button[aria-pressed=true]{background:#167d62;color:white}svg{width:100%;display:block}svg text{font:11px system-ui;fill:var(--muted)}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px}.swatch{display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:5px}.readouts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.readout{background:#f6f8f7;border-radius:7px;padding:8px;overflow-wrap:anywhere}.readout strong{font:600 18px/1.5 ui-monospace,monospace;display:block}.readout small{display:block;color:var(--muted);font-size:11px}.events{max-height:350px;overflow:auto}.event{display:flex;gap:12px;border-bottom:1px solid var(--line);padding:7px 0}.event button{min-width:100px}pre{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}details summary{cursor:pointer}a{color:var(--green)}.annotation{border-left:3px solid #d29352;padding-left:10px}#zoomDescription{font-weight:600}.chart-summary{font:12px ui-monospace,monospace;color:var(--muted)}@media(max-width:900px){main{padding:14px}.grid{grid-template-columns:1fr}.readouts{grid-template-columns:repeat(2,1fr)}.stagegrid{grid-template-columns:1fr 1fr}}
</style><main>
<h1>LabSim <span class="muted">/</span> Progress v1.2</h1><p class="muted">原任务判分、历史阶段覆盖、当前有效进度与原始几何诊断分别展示。未知证据保持 unknown；Progress 不修改原任务判分或 reward。</p>
<div id="outcome" class="facts"></div>
<section class="card"><h2>真实侧视 / 腕视录像</h2><div id="videos" class="videos"></div><p id="videoNote" class="muted"></p><input id="seek" aria-label="simulation time" type="range" min="0" step="0.001"><div id="cursor" class="facts" aria-live="polite"></div><p id="sampling" class="muted"></p></section>
<section class="card"><h2>光标 · 原始控制步读数</h2><p class="muted">以下数值属于所示“实际样本时间”，采用请求时间之前最近的原始控制端点；不插值，也不读取抽稀曲线点。</p><div id="readouts" class="readouts"></div><p id="gates" class="annotation"></p></section>
<section class="card"><h2>阶段跳转与局部缩放</h2><div id="jumpButtons" class="tools"></div><p id="zoomDescription"></p><div class="tools"><button id="zoomFull">全程</button><button id="zoomContact">对准—撤离局部</button><button id="zoomAround">光标 ±2 s</button><label>起点 s <input id="zoomStart" type="number" step="0.001"></label><label>终点 s <input id="zoomEnd" type="number" step="0.001"></label><button id="zoomApply">应用区间</button></div><p class="muted">每个图按所选区间独立缩放；局部图保留原始控制步极值、unknown 断段、首次确认与稳定窗口中断标记。虚线为已声明阈值，不是接触精度。</p></section>
<section class="card"><h2>九阶段 · 物理条件与合法后继</h2><p class="muted">原始当前条件与历史首次达成保留；“已完成并正常后继”依据因果操作链路。未确认承托不等同于已掉落。</p><div id="timeline" class="lanes"></div><div id="stages" class="stagegrid"></div></section>
<div id="charts" class="grid"></div>
<section class="card"><h2>事件归并 · 首次达到 / 交接变化 / 最终稳定</h2><div id="eventCounts" class="facts"></div><div id="groupedEvents" class="events"></div><details><summary>全部原始条件切换与尝试事件</summary><div id="events" class="events"></div></details></section>
<section class="card"><h2>原判分、证据与可复现信息</h2><details open><summary>原任务结果与 Progress 终局</summary><pre id="terminal"></pre></details><details><summary>输入范围与来源身份</summary><pre id="identity"></pre></details><details><summary>尝试、漂移区间与输出统计</summary><pre id="recording"></pre></details><p><a href="progress_summary.json">完整 Summary</a> · <a href="progress_config.resolved.json">Resolved 配置</a> · <a href="progress_events.jsonl">完整事件流</a> · <a href="progress_v1.jsonl.gz">完整控制步 sidecar</a></p></section>
</main><script type="application/json" id="data">__PROGRESS_DATA__</script><script>
'use strict';
const D=JSON.parse(document.getElementById('data').textContent),K=D.metric_keys,E=D.events;
const stages=['approach_grasp','grasp','extract','transport','align','insert','support_transfer','release_retreat','stable_complete'];
const labels=['接近抓取','建立抓持','离架','持物搬运','目标对准','有效插入','支撑交接','释放与撤离','稳定完成'];
const statusText={active:'当前正在执行',completed_followed:'已完成并正常后继',temporarily_unmet:'条件暂时失效',evidenced_failure:'有证据的失败 / 异常',evidence_missing:'证据不足',not_started:'尚未达到',unknown:'旧记录未提供状态解释'};
const holdText={target_supported:'目标承托',gripper_held:'夹爪持物',source_supported:'来源承托',unsupported_or_lost:'承托未确认',support_unconfirmed:'承托未确认',unsupported_with_observed_loss:'已观察抓持丢失',unknown:'承托证据未知'};
const unpack=a=>({t:a[0],t_obs:a[1],stage:a[2],highest_stage:a[3],hold_state:a[4],attempt_id:a[5],continuous:a[6],coverage:a[7],insertion_progress_applicable:a[8],vector:a[9],statuses:a[10].map(i=>D.status_names[i]),metrics:Object.fromEntries(K.map((k,i)=>[k,a[11][i]])),missing:Object.fromEntries(a[12].map(([i,j])=>[K[i],D.strings[j]])),status_reasons:a[13].map(i=>i===null?null:D.strings[i]),effective:a[14],gate_reasons:{not_applicable:a[15][0].map(i=>D.strings[i]),unknown:a[15][1].map(i=>D.strings[i])},hold_state_user:a[16]});
const R=D.rows.map(unpack),P=D.plot_indices.map(i=>R[i]),min=R.length?Math.min(0,R[0].t_obs):0,max=R.length?R.at(-1).t:1;
const seek=document.getElementById('seek');seek.min=min;seek.max=max;seek.value=min;
const finite=v=>typeof v==='number'&&Number.isFinite(v),fmt=(v,n=3)=>finite(v)?v.toFixed(n):'unknown';
const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x},fact=text=>el('span',text,'fact');
const original=D.original_result?.task_success??D.original_result?.success??D.identity.original_labels?.task_success??null;
document.getElementById('outcome').append(fact('原任务最终成功: '+String(original)),fact('Progress 阶段覆盖完成: '+String(D.summary.progress_complete)),fact('独立操作尝试: '+(D.summary.attempts?.length??0)),fact('报告: '+D.report_version));
const V=[];for(const v of D.videos){const f=el('figure'),m=el('video');m.controls=true;m.preload='metadata';m.src=v.src;f.append(m,el('figcaption',v.name+' · 实际录制显示副本 / 原视频'));document.getElementById('videos').append(f);V.push(m)}
const ts=D.timestamps.frame_simulation_times_s||[],fps=D.timestamps.nominal_fps||30;
document.getElementById('videoNote').textContent=V.length?(ts.length?'按原 video_timestamps.json 的真实帧仿真时间定位；视频帧时间与控制样本时间分别记录。':'缺 video_timestamps.json，视频与仿真时间关联 unknown。'):'未关联视频；可通过 --episode 指向实际录像，或使用便携报告工具。';
const nearest=(a,t)=>{let l=0,h=a.length-1;while(l<h){const m=(l+h)>>1;if(a[m]<t)l=m+1;else h=m}return l>0&&Math.abs(a[l-1]-t)<Math.abs(a[l]-t)?l-1:l};
const stateAt=t=>{let l=0,h=R.length;while(l<h){const m=(l+h)>>1;if(R[m].t<=t+1e-8)l=m+1;else h=m}if(l)return R[l-1];const f=D.first_control_observation;return f&&f.t<=t+1e-8?f:D.reset_snapshot};
const causalMilestone=(s,t)=>{const out={first_candidate_t:null,first_confirmed_t:null,last_confirmed_t:null,confirmation_count:0};for(const e of E){if(e.t>t+1e-8)break;if(e.name===s+'_candidate'&&out.first_candidate_t===null)out.first_candidate_t=e.t;if(e.name===s+'_confirmed'){out.first_confirmed_t??=e.t;out.last_confirmed_t=e.t;out.confirmation_count++}}return out};
let range=[min,max],requestedTime=min;
const readSpecs=[['target_lateral_error_m','目标横向误差','mm',1000],['target_tilt_rad','倾角','°',180/Math.PI],['target_yaw_error_rad','绕轴误差','°',180/Math.PI],['raw_axial_depth_m','原始轴向深度','mm',1000],['raw_depth_fraction','原始深度比例（未截断）','ratio',1],['valid_insertion_progress','当前有效插入进度','0–1',1],['grasp_relative_translation_m','抓持相对平移','mm',1000],['grasp_relative_rotation_rad','抓持相对旋转','°',180/Math.PI],['target_bottom_support_N','净竖直目标承托力','N',1],['target_bottom_gap_m','底部间隙','mm',1000],['gripper_object_clearance_m','整手净距下界','mm',1000],['stable_duration_s','连续稳定时长','s',1],['grasp_approach_position_error_m','接近位置误差','mm',1000],['grasp_approach_orientation_error_rad','接近姿态误差','°',180/Math.PI],['approach_position_quality','接近位置质量','0–1',1],['approach_orientation_quality','接近姿态质量','0–1',1]];
function display(t,sync=true){requestedTime=t;const r=stateAt(t),frame=ts.length?nearest(ts,t):null;
 document.getElementById('cursor').replaceChildren(fact('请求仿真时间 '+fmt(t,6)+' s'),fact('实际样本时间 '+fmt(r?.t,6)+' s'),fact('样本滞后 '+fmt(r?Math.max(0,t-r.t):null,6)+' s'),fact('阶段 '+(r?.stage||'unknown')),fact('历史最高 '+(r?.highest_stage||'unknown')),fact('承托 '+(holdText[r?.hold_state_user]||r?.hold_state_user||r?.hold_state||'unknown')),fact('当前有效阶段进度 '+fmt(r?.continuous)),fact('历史覆盖 '+fmt(r?.coverage)),fact('视频帧时间 '+fmt(frame===null?null:ts[frame],6)+' s'));
 const target=document.getElementById('stages');target.replaceChildren();stages.forEach((s,i)=>{const st=causalMilestone(s,r?.t??t),v=r?.vector?.[i]??null,status=r?.statuses?.[i]||'unknown',x=el('div',undefined,'stage');x.append(el('b',labels[i]+' / '+s),el('div',statusText[status]||status,status==='evidenced_failure'?'failure':status==='evidence_missing'?'unknown':status==='completed_followed'?'yes':'muted'),el('div','原始当前条件: '+(v===null?'unknown':v?'满足':'未满足'),v===null?'unknown':v?'yes':'no'),el('div','首次候选 '+fmt(st.first_candidate_t)+' s · 首次确认 '+fmt(st.first_confirmed_t)+' s'),el('div','最后确认 '+fmt(st.last_confirmed_t)+' s · 确认次数 '+st.confirmation_count),el('div','首次候选→首次确认耗时 '+fmt(finite(st.first_candidate_t)&&finite(st.first_confirmed_t)?st.first_confirmed_t-st.first_candidate_t:null)+' s'));if(r?.status_reasons?.[i])x.append(el('small',r.status_reasons[i],'muted'));target.append(x)});
 const readouts=document.getElementById('readouts');readouts.replaceChildren();for(const [key,label,unit,scale]of readSpecs){const value=r?.metrics?.[key],card=el('div',undefined,'readout');card.dataset.metric=key;card.append(el('span',label),el('strong',finite(value)?fmt(value*scale,key==='valid_insertion_progress'?4:3)+' '+unit:'unknown'),el('small',finite(value)?'控制样本 '+fmt(r.t,6)+' s':r?.missing?.[key]||'missing_control_sample'));readouts.append(card)}
 const gates=r?.gate_reasons||{},why=[...(gates.not_applicable||[]),...(gates.unknown||[])];document.getElementById('gates').textContent='有效插入适用性: '+String(r?.insertion_progress_applicable??'unknown')+'；'+(why.length?why.join('；'):r?.insertion_progress_applicable===true?'正确目标、入口区域、姿态与当次合法操作链路门控通过。':'缺少门控记录；有效进度保持 unknown，不从原始深度推断。');
 document.querySelectorAll('.cursorline').forEach(x=>{const p=90+(t-range[0])/(range[1]-range[0]||1)*880;x.setAttribute('x1',p);x.setAttribute('x2',p);x.style.display=t<range[0]||t>range[1]?'none':''});
 if(sync&&frame!==null){const mt=frame/fps;V.forEach(v=>{if(Math.abs(v.currentTime-mt)>.02)v.currentTime=mt})}}
seek.addEventListener('input',()=>display(+seek.value));V.forEach((v,index)=>v.addEventListener('timeupdate',()=>{if(!v.paused&&ts.length){const t=ts[Math.min(ts.length-1,Math.round(v.currentTime*fps))];seek.value=t;display(t,false);V.forEach((other,j)=>{if(j!==index&&Math.abs(other.currentTime-v.currentTime)>.15)other.currentTime=v.currentTime})}}));
document.getElementById('sampling').textContent=`全部 ${D.display_sampling.cursor_rows} 个原始控制端点用于光标读取；全程曲线展示 ${D.display_sampling.displayed_rows} 点。局部区间绘制全部原始控制端点。样本时间与请求时间明确分列；物理采样峰值另见 attempt 漂移统计。`;
const NS='http://www.w3.org/2000/svg',colors=['#167d62','#a05936','#5678bc'];function svgEl(tag,attrs,text){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs||{}))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n}
function base(height){const svg=svgEl('svg',{viewBox:`0 0 1000 ${height}`,role:'img'});svg.append(svgEl('line',{class:'cursorline',x1:90,x2:90,y1:5,y2:height-15,stroke:'#172f36','stroke-width':1,opacity:.6}));return svg}
const specs=[{id:'lateral',title:'目标横向误差',unit:'mm',series:[['target_lateral_error_m','横向',1000]],thresholds:[['alignment_lateral_m','对准预算',1000]]},{id:'orientation',title:'目标姿态误差',unit:'°',series:[['target_tilt_rad','倾角',180/Math.PI],['target_yaw_error_rad','绕轴',180/Math.PI]],thresholds:[['alignment_tilt_rad','倾角预算',180/Math.PI],['alignment_yaw_rad','绕轴预算',180/Math.PI]]},{id:'depth',title:'原始轴向投影深度',unit:'mm',series:[['raw_axial_depth_m','原始深度',1000],['target_depth_m','目标深度',1000]]},{id:'effective',title:'有效任务进度',unit:'0–1',fixed:[0,1],series:[['valid_insertion_progress','有效插入',1],['approach_position_quality','接近位置质量',1],['approach_orientation_quality','接近姿态质量',1]]},{id:'translation',title:'抓持相对平移',unit:'mm',series:[['grasp_relative_translation_m','相对平移',1000]],thresholds:[['grasp_translation_m','持物诊断阈值',1000]]},{id:'rotation',title:'抓持相对旋转',unit:'°',series:[['grasp_relative_rotation_rad','相对旋转',180/Math.PI]],thresholds:[['grasp_rotation_rad','持物诊断阈值',180/Math.PI]]},{id:'support',title:'净竖直目标承托力',unit:'N',series:[['target_bottom_support_N','目标底部承托',1]],thresholds:[['support_min_N','承托门槛',1]]},{id:'clearance',title:'底部间隙与整手净距',unit:'mm',series:[['target_bottom_gap_m','底部间隙',1000],['gripper_object_clearance_m','整手净距下界',1000]],thresholds:[['support_gap_m','允许底部间隙',1000],['retreat_clearance_m','撤离净距',1000]]},{id:'stability',title:'连续稳定窗口',unit:'s',series:[['stable_duration_s','稳定时长',1]],thresholds:[['stable_duration_s','要求时长',1]]},{id:'stablepos',title:'稳定窗口位置漂移',unit:'mm',series:[['stable_position_drift_m','位置漂移',1000]],thresholds:[['stable_position_drift_m','允许漂移',1000]]},{id:'stableangle',title:'稳定窗口姿态变化',unit:'°',series:[['stable_orientation_change_rad','姿态变化',180/Math.PI]],thresholds:[['stable_orientation_change_rad','允许变化',180/Math.PI]]},{id:'approach',title:'接近 / 搬运位置诊断',unit:'mm',series:[['grasp_approach_position_error_m','接近抓取',1000],['preinsert_distance_m','预插入距离',1000],['source_bottom_envelope_clearance_m','离架净空',1000]]}];
function selectedRows(){return range[0]===min&&range[1]===max?P:R.filter(r=>r.t>=range[0]&&r.t<=range[1])}
function markers(svg,x){for(const e of E){if(e.t<range[0]||e.t>range[1])continue;const first=e.name.endsWith('_confirmed')&&causalMilestone(e.name.slice(0,-10),e.t).first_confirmed_t===e.t;if(!first&&e.name!=='stable_window_interrupted')continue;svg.append(svgEl('line',{x1:x(e.t),x2:x(e.t),y1:20,y2:178,stroke:e.name==='stable_window_interrupted'?'#b33c3c':'#889d97','stroke-dasharray':e.name==='stable_window_interrupted'?'2 2':'4 5',opacity:.6}));}}
function renderCharts(){const box=document.getElementById('charts');box.replaceChildren();const control=R.filter(r=>r.t>=range[0]&&r.t<=range[1]),plot=selectedRows(),x=t=>90+(t-range[0])/(range[1]-range[0]||1)*880;
 for(const spec of specs){const card=el('section',undefined,'card');card.dataset.chart=spec.id;card.append(el('h2',spec.title+' / '+spec.unit));const svg=base(220),all=[];for(const [key,_,scale]of spec.series)for(const r of control)if(finite(r.metrics[key]))all.push(r.metrics[key]*scale);const rules=(spec.thresholds||[]).filter(([key])=>finite(D.thresholds[key])).map(([key,label,scale])=>[D.thresholds[key]*scale,label]);let lo=spec.fixed?.[0]??(all.length?Math.min(...all):0),hi=spec.fixed?.[1]??(all.length?Math.max(...all):1);for(const [v]of rules){lo=Math.min(lo,v);hi=Math.max(hi,v)}const rawLo=all.length?Math.min(...all):null,rawHi=all.length?Math.max(...all):null;if(hi===lo){lo-=.5;hi+=.5}else if(!spec.fixed){const pad=(hi-lo)*.06;lo-=pad;hi+=pad}const y=v=>175-(v-lo)/(hi-lo)*145;
 svg.append(svgEl('text',{x:0,y:32},fmt(hi,4)),svgEl('text',{x:0,y:175},fmt(lo,4)),svgEl('text',{x:90,y:206},fmt(range[0])+' s'),svgEl('text',{x:920,y:206},fmt(range[1])+' s'));for(const [v,label]of rules){svg.append(svgEl('line',{x1:90,x2:970,y1:y(v),y2:y(v),stroke:'#a86b35','stroke-dasharray':'5 4'}),svgEl('text',{x:94,y:Math.max(17,y(v)-3)},label+' '+fmt(v,4)+' '+spec.unit))}markers(svg,x);const legend=el('div',undefined,'legend');
 spec.series.forEach(([key,label,scale],i)=>{let segment='',segments=[],missing=false;for(const r of plot){const v=r.metrics[key];if(finite(v)){segment+=x(r.t).toFixed(3)+','+y(v*scale).toFixed(3)+' ';if(missing)missing=false}else{if(segment){segments.push(segment);segment=''}missing=true}}if(segment)segments.push(segment);for(const points of segments)svg.append(svgEl('polyline',{points,fill:'none',stroke:colors[i%3],'stroke-width':1.5}));const item=el('span'),sw=el('i',undefined,'swatch');sw.style.background=colors[i%3];item.append(sw,document.createTextNode(label));legend.append(item)});if(!all.length)svg.append(svgEl('text',{x:410,y:100},'unknown · 无可用证据'));card.append(legend,svg,el('div','所选区间原始控制端点极值: '+fmt(rawLo,6)+' — '+fmt(rawHi,6)+' '+spec.unit+' · '+control.length+' control samples','chart-summary'));box.append(card)}
 const timeline=base(325),T=[D.reset_snapshot,D.first_control_observation,...selectedRows()].filter(r=>r&&r.t>=range[0]&&r.t<=range[1]).sort((a,b)=>a.t-b.t);stages.forEach((s,i)=>{const y=8+i*32;timeline.append(svgEl('text',{x:0,y:y+16},labels[i]));for(let j=0;j<T.length;j++){const r=T[j],end=T[j+1]?.t??range[1],v=r.vector?.[i]??null;timeline.append(svgEl('rect',{x:x(r.t),y,width:Math.max(.4,x(end)-x(r.t)),height:22,fill:v===null?'#ccd2d6':v?'#258c71':'#f0ddc7'}))}});document.getElementById('timeline').replaceChildren(timeline);display(requestedTime,false)}
function setZoom(a,b){range=[Math.max(min,a),Math.min(max,b)];if(range[1]<=range[0])range=[min,max];document.getElementById('zoomStart').value=range[0].toFixed(6);document.getElementById('zoomEnd').value=range[1].toFixed(6);document.getElementById('zoomDescription').textContent='图表范围 '+fmt(range[0],3)+' — '+fmt(range[1],3)+' s';renderCharts()}
function stageTime(s){return E.find(e=>e.name===s+'_confirmed')?.t??D.summary.milestones?.[s]?.first_confirmed_t??null}
for(const s of ['align','insert','support_transfer','released','retreated','stable_complete']){const i=stages.indexOf(s),b=el('button',s==='released'?'实际释放':s==='retreated'?'实际撤离':labels[i]);b.dataset.stage=s;const t=stageTime(s);b.disabled=!finite(t);b.onclick=()=>{seek.value=t;display(t);setZoom(Math.max(min,t-2),Math.min(max,t+3))};document.getElementById('jumpButtons').append(b)}
document.getElementById('zoomFull').onclick=()=>setZoom(min,max);document.getElementById('zoomContact').onclick=()=>{const a=stageTime('align'),b=stageTime('retreated');if(finite(a))setZoom(a-1,finite(b)?b+1:max)};document.getElementById('zoomAround').onclick=()=>setZoom(requestedTime-2,requestedTime+2);document.getElementById('zoomApply').onclick=()=>{const a=+document.getElementById('zoomStart').value,b=+document.getElementById('zoomEnd').value;if(finite(a)&&finite(b)&&b>a)setZoom(a,b)};
const addEvent=(box,e,text)=>{const row=el('div',undefined,'event'),button=el('button',fmt(e.t,6)+' s');button.onclick=()=>{seek.value=e.t;display(e.t)};row.append(button,el('span',text));box.append(row)};
const rawBox=document.getElementById('events');for(const e of E)addEvent(rawBox,e,e.name+' · attempt '+String(e.attempt_id)+' · '+(e.reason||e.outcome||''));if(!E.length)rawBox.textContent='无事件。';
const confirmed=E.filter(e=>e.name.endsWith('_confirmed')),lost=E.filter(e=>e.name.endsWith('_condition_lost'));document.getElementById('eventCounts').append(fact('原始事件 '+E.length),fact('条件确认 '+confirmed.length),fact('条件失效切换 '+lost.length),fact('操作尝试 '+(D.summary.attempts?.length??0)));
const groups=document.getElementById('groupedEvents');for(let i=0;i<stages.length;i++){const s=stages[i],changes=E.filter(e=>e.name===s+'_confirmed'||e.name===s+'_condition_lost'),first=changes.find(e=>e.name.endsWith('_confirmed'));if(first)addEvent(groups,first,labels[i]+' · 首次确认；确认 '+changes.filter(e=>e.name.endsWith('_confirmed')).length+' 次，原始条件失效 '+changes.filter(e=>e.name.endsWith('_condition_lost')).length+' 次；不视为重复任务成功')}
const transfer=E.filter(e=>/^(align|insert|support_transfer)_(confirmed|condition_lost)$/.test(e.name));if(transfer.length)addEvent(groups,transfer[0],'对准 / 插入 / 交接变化区间 '+fmt(transfer[0].t)+' — '+fmt(transfer.at(-1).t)+' s · '+transfer.length+' 个原始条件事件');for(const e of E.filter(e=>e.name==='attempt_started'||e.name==='attempt_ended'||e.name==='attempt_outcome_updated'||e.name==='stable_window_interrupted'))addEvent(groups,e,e.name+' · attempt '+String(e.attempt_id)+' · '+(e.reason||e.outcome||''));
document.getElementById('terminal').textContent=JSON.stringify({original_task_result:D.original_result,progress_stage_coverage_complete:D.summary.progress_complete,termination_domain:D.summary.termination_domain,unfinished_requirement:D.summary.unfinished_requirement,failure_observation:D.summary.failure_observation},null,2);document.getElementById('identity').textContent=JSON.stringify({report_version:D.report_version,identity:D.identity,evidence:D.evidence,video_sources:D.videos,display_sampling:D.display_sampling},null,2);document.getElementById('recording').textContent=JSON.stringify({attempts:D.summary.attempts,recording:D.summary.recording,integrity:D.summary.output_integrity},null,2);
// Small read-only surface for reproducible browser acceptance checks.
window.LabSimProgressReport={version:D.report_version,data:D,stateAt,display,setZoom,getRange:()=>range.slice(),getRequestedTime:()=>requestedTime};
setZoom(min,max);display(min);
</script></html>'''
