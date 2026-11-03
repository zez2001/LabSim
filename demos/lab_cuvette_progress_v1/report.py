"""Self-contained HTML/SVG Progress reports linked to genuine recorded movies."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from .io import iter_json_rows

PLOT_METRICS = ('target_lateral_error_m', 'target_tilt_rad', 'target_yaw_error_rad',
    'raw_depth_m', 'target_depth_m', 'grasp_relative_translation_m',
    'grasp_relative_rotation_rad', 'target_bottom_support_N', 'target_bottom_gap_m',
    'gripper_object_clearance_m', 'stable_duration_s', 'gripper_opening_m',
    'tcp_object_distance_m', 'both_fingers_open_and_detached', 'stable_position_drift_m',
    'stable_orientation_change_rad', 'source_bottom_envelope_clearance_m',
    'preinsert_distance_m', 'grasp_approach_position_error_m')


def _state_row(state, t_obs=None):
    metrics = {}
    for key in PLOT_METRICS:
        metric = state.get('metrics', {}).get(key, {})
        value = metric.get('value') if metric.get('available') else None
        metrics[key] = int(value) if isinstance(value, bool) else value
    return dict(t=state.get('t'), t_obs=state.get('t') if t_obs is None else t_obs,
        stage=state.get('current_stage'), vector=state.get('stage_vector', []),
        continuous=state.get('current_stage_continuous'), metrics=metrics,
        hold_state=state.get('hold_state', 'unknown'))


def _plot_rows(rows, events, limit=2000):
    """Retain state/unknown boundaries, all event neighbours, and bucket extrema.

    This is display-only reduction. Every original transition remains in the
    gzip sidecar. Extrema are chosen per plotted metric to retain brief spikes.
    """
    if len(rows) <= limit:
        return rows
    import bisect
    mandatory = {0, len(rows) - 1}
    for i in range(1, len(rows)):
        before, after = rows[i - 1], rows[i]
        if ((before['stage'], before['hold_state'], before['vector']) !=
                (after['stage'], after['hold_state'], after['vector']) or
                any((before['metrics'][k] is None) != (after['metrics'][k] is None) for k in PLOT_METRICS)):
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
            valid = [(rows[i]['metrics'][key], i) for i in range(start, end)
                     if isinstance(rows[i]['metrics'][key], (float, int))]
            if valid:
                selected.update((min(valid)[1], max(valid)[1]))
    return [rows[i] for i in sorted(selected)]


def generate_report(progress_directory, episode_directory=None, *, copy_videos=False):
    progress = Path(progress_directory).resolve()
    summary = json.loads((progress / 'progress_summary.json').read_text())
    if episode_directory is None:
        episode_directory = summary.get('metadata', {}).get('source_trajectory', {}).get('episode_directory')
    episode = Path(episode_directory).resolve() if episode_directory else None
    rows = []
    for row in iter_json_rows(progress / 'progress_v1.jsonl.gz'):
        state = row.get('after') or {}
        rows.append(_state_row(dict(state, t=row['t_next']), row['t_obs']))
    events = list(iter_json_rows(progress / 'progress_events.jsonl'))
    source_rows = len(rows)
    rows = _plot_rows(rows, events)
    videos, timestamps = [], {}
    if episode is not None:
        timestamp_path = episode / 'video_timestamps.json'
        if timestamp_path.is_file():
            timestamps = json.loads(timestamp_path.read_text())
        for name in ('side_camera.mp4', 'wrist_camera.mp4'):
            path = episode / name
            if path.is_file():
                if copy_videos:
                    destination = progress / 'media' / name
                    destination.parent.mkdir(exist_ok=True)
                    if destination.exists():
                        raise FileExistsError(destination)
                    shutil.copy2(path, destination)
                    path = destination
                videos.append(dict(name=name, src=os.path.relpath(path, progress)))
    data = dict(rows=rows, events=events, videos=videos, timestamps=timestamps,
        display_sampling=dict(original_transitions=source_rows, displayed_rows=len(rows),
            method='Display-only per-metric bucket extrema; all event, stage/hold and unknown boundaries retained'),
        reset_snapshot=_state_row(summary['reset_snapshot']) if summary.get('reset_snapshot') else None,
        first_control_observation=_state_row(summary['first_control_observation']) if summary.get('first_control_observation') else None,
        summary={key: summary.get(key) for key in ('progress_complete', 'termination_domain',
            'unfinished_requirement', 'failure_observation', 'attempts', 'milestones',
            'output_integrity', 'recording', 'config_sha256')},
        identity=summary.get('metadata', {}).get('source_trajectory', {}),
        evidence=summary.get('metadata', {}).get('input_evidence', {}))
    # A JSON script element is data, never executable trajectory-supplied text.
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    target = progress / 'progress_report.html'
    target.write_text(_HTML.replace('__PROGRESS_DATA__', payload), encoding='utf-8')
    return target


_HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LabSim · Progress v1</title>
<style>
:root{color-scheme:light;--ink:#14252d;--muted:#62777c;--green:#167d62;--line:#dbe5e5;--bg:#f1f5f4}
*{box-sizing:border-box}body{font:14px/1.5 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
main{max-width:1440px;margin:auto;padding:26px}h1{font-size:26px;margin:0}h2{font-size:16px;margin:0 0 12px}
.muted{color:var(--muted)}.card{background:white;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid .card{margin:0}
.videos{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:240px}video{width:100%;background:#10191c;border-radius:8px}figcaption{color:var(--muted)}
input[type=range]{width:100%;accent-color:var(--green)}.facts{display:flex;gap:12px;flex-wrap:wrap}.fact{padding:8px 12px;border-radius:7px;background:#edf3f1}
svg{width:100%;display:block}svg text{font:11px system-ui;fill:var(--muted)}.lanes svg text{font-size:12px}
.stagegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stage{border:1px solid var(--line);padding:10px;border-radius:8px}.stage b{display:block}
.yes{color:var(--green)}.no{color:#b17736}.unknown{color:#8b9398}button{border:1px solid var(--line);background:#f6faf8;border-radius:7px;padding:6px 10px;cursor:pointer}
.events{max-height:360px;overflow:auto}.event{display:flex;gap:12px;border-bottom:1px solid var(--line);padding:8px 0}.event button{min-width:92px}
pre{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}details summary{cursor:pointer}a{color:var(--green)}
@media(max-width:800px){main{padding:14px}.grid{grid-template-columns:1fr}.stagegrid{grid-template-columns:1fr 1fr}}
</style><main>
<h1>LabSim <span class="muted">/</span> Progress v1</h1>
<p class="muted">实际物理证据 → 当前条件 → 历史里程碑。未知数据保持 unknown。Progress 不更改原独立判分或 reward。</p>
<div id="outcome" class="facts"></div>
<section class="card"><h2>真实侧视 / 腕视录像</h2><div id="videos" class="videos"></div><p id="videoNote" class="muted"></p>
<input id="seek" aria-label="simulation time" type="range" min="0" step="0.001"><div class="facts" id="cursor"></div><p id="sampling" class="muted"></p></section>
<section class="card"><h2>九阶段 · 当前条件与历史达成</h2><p class="muted">绿色：当前满足；浅橙：当前未满足；灰色：证据未知。虚线：历史首次确认后。历史达成不会阻止当前回退。</p><div class="lanes" id="timeline"></div><div class="stagegrid" id="stages"></div></section>
<div class="grid" id="charts"></div>
<section class="card"><h2>事件与确认时间</h2><div id="events" class="events"></div></section>
<section class="card"><h2>证据范围、原判分及完整性</h2><details open><summary>终局与未完成要求</summary><pre id="terminal"></pre></details>
<details><summary>输入覆盖与来源身份</summary><pre id="identity"></pre></details><details><summary>尝试与输出统计</summary><pre id="recording"></pre></details>
<p><a href="progress_summary.json">完整 Summary</a> · <a href="progress_config.resolved.json">Resolved 配置</a> · <a href="progress_events.jsonl">稀疏事件</a></p></section>
</main><script type="application/json" id="data">__PROGRESS_DATA__</script><script>
'use strict';
const D=JSON.parse(document.getElementById('data').textContent),R=D.rows,E=D.events;
const stages=['approach_grasp','grasp','extract','transport','align','insert','support_transfer','release_retreat','stable_complete'];
const labels=['接近抓取','建立抓持','离架','持物搬运','目标对准','有效插入','支撑交接','释放与撤离','稳定完成'];
const min=R.length?Math.min(0,R[0].t_obs):0,max=R.length?R[R.length-1].t:1;
const seek=document.getElementById('seek');seek.min=min;seek.max=max;seek.value=min;
const fmt=(v,n=3)=>Number.isFinite(v)?v.toFixed(n):'unknown';
const el=(tag,text,cls)=>{let x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x};
const fact=(text)=>el('span',text,'fact');
let O=document.getElementById('outcome');O.append(fact('Progress: '+String(D.summary.progress_complete)),fact('输出: '+(D.summary.output_integrity?.status||'unknown')),fact('证据: '+(D.evidence.mode||'unknown')));
let V=[];for(const v of D.videos){let f=el('figure'),m=el('video');m.controls=true;m.preload='metadata';m.src=v.src;f.append(m,el('figcaption',v.name+' · 实际仿真录制'));document.getElementById('videos').append(f);V.push(m)}
const ts=D.timestamps.frame_simulation_times_s||[],fps=D.timestamps.nominal_fps||30;
document.getElementById('videoNote').textContent=V.length?(ts.length?'按原 video_timestamps.json 的帧仿真时间对齐；滑块定位到最近真实帧。':'缺 video_timestamps.json，视频与仿真时间关联未知；不使用假定偏移。'):'未找到原始 MP4；请保留源轨迹路径，或使用 --copy-videos 生成可移交副本。';
const nearest=(a,t)=>{let l=0,h=a.length-1;while(l<h){let m=(l+h)>>1;if(a[m]<t)l=m+1;else h=m}return l>0&&Math.abs(a[l-1]-t)<Math.abs(a[l]-t)?l-1:l};
const stateAt=(t)=>{let l=0,h=R.length;while(l<h){let m=(l+h)>>1;if(R[m].t<=t+1e-8)l=m+1;else h=m}if(l)return R[l-1];let f=D.first_control_observation;return f&&f.t<=t+1e-8?f:D.reset_snapshot};
const current=(r,s,i)=>r?.vector?.[i]??null;
document.getElementById('sampling').textContent=`展示 ${D.display_sampling.displayed_rows} / ${D.display_sampling.original_transitions} 个控制端点：保留每指标区间极值、全部事件邻点、阶段/承托/未知边界。完整逐步值保存在 progress_v1.jsonl.gz；滑块采用所选时刻之前的已保存展示端点。`;
function display(t,sync=true){let r=stateAt(t);document.getElementById('cursor').replaceChildren(fact('仿真时间 '+fmt(t)+' s'),fact('阶段 '+(r?.stage||'unknown')),fact('承托 '+(r?.hold_state||'unknown')));
let target=document.getElementById('stages');target.replaceChildren();stages.forEach((s,i)=>{let st=D.summary.milestones?.[s]||{},v=current(r,s,i),confirmed=Number.isFinite(st.first_confirmed_t)&&st.first_confirmed_t<=t+1e-8,x=el('div',undefined,'stage');x.append(el('b',labels[i]+' / '+s),el('span','当前: '+(v===null?'unknown':v?'满足':'未满足'),v===null?'unknown':v?'yes':'no'),el('div','历史: '+(confirmed?'已达成':'未确认')+' · 首次确认 '+(confirmed?fmt(st.first_confirmed_t)+' s':'尚未确认')));target.append(x)});
document.querySelectorAll('.cursorline').forEach(x=>{let p=90+(t-min)/(max-min||1)*880;x.setAttribute('x1',p);x.setAttribute('x2',p)});
if(sync&&ts.length){let mt=nearest(ts,t)/fps;V.forEach(v=>{if(Math.abs(v.currentTime-mt)>.02)v.currentTime=mt})}}
seek.addEventListener('input',()=>display(+seek.value));
V.forEach((v,index)=>v.addEventListener('timeupdate',()=>{if(!v.paused&&ts.length){let t=ts[Math.min(ts.length-1,Math.round(v.currentTime*fps))];seek.value=t;display(t,false);V.forEach((other,j)=>{if(j!==index&&Math.abs(other.currentTime-v.currentTime)>.15)other.currentTime=v.currentTime})}}));
const NS='http://www.w3.org/2000/svg';function svgEl(tag,attrs,text){let n=document.createElementNS(NS,tag);for(let [k,v]of Object.entries(attrs||{}))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n}
function base(height){let svg=svgEl('svg',{viewBox:`0 0 1000 ${height}`,role:'img'});svg.append(svgEl('line',{class:'cursorline',x1:90,x2:90,y1:5,y2:height-15,stroke:'#172f36','stroke-width':1,opacity:.45}));return svg}
let timeline=base(320),T=[D.reset_snapshot,D.first_control_observation,...R].filter(Boolean).sort((a,b)=>a.t-b.t);stages.forEach((s,i)=>{let y=8+i*32;timeline.append(svgEl('text',{x:0,y:y+17},labels[i]));for(let j=0;j<T.length;j++){let r=T[j],n=T[Math.min(T.length-1,j+1)],v=current(r,s,i),x=90+(r.t-min)/(max-min||1)*880,w=Math.max(1,(n.t-r.t)/(max-min||1)*880);timeline.append(svgEl('rect',{x,y,width:w,height:23,fill:v===null?'#c9d0d3':v?'#258c71':'#f3d9b6'}))}let milestone=D.summary.milestones?.[s],t=milestone?.first_confirmed_t;if(Number.isFinite(t)){timeline.append(svgEl('line',{x1:90+(t-min)/(max-min||1)*880,x2:970,y1:y+26,y2:y+26,stroke:'#167d62','stroke-dasharray':'5 3'}))}});document.getElementById('timeline').append(timeline);
const specs=[['横向与姿态误差',[['target_lateral_error_m','横向 mm',1000],['target_tilt_rad','倾角 °',180/Math.PI],['target_yaw_error_rad','轴向角 °',180/Math.PI]]],['插入深度',[['raw_depth_m','原始深度 mm',1000],['target_depth_m','目标深度 mm',1000]]],['抓持相对滑移',[['grasp_relative_translation_m','平移 mm',1000],['grasp_relative_rotation_rad','旋转 °',180/Math.PI]]],['目标承托与撤离净距',[['target_bottom_support_N','底部承托 N',1],['target_bottom_gap_m','底部间隙 mm',1000],['gripper_object_clearance_m','夹爪净距 mm',1000]]],['稳定窗口',[['stable_duration_s','连续稳定 s',1],['stable_position_drift_m','漂移 mm',1000],['stable_orientation_change_rad','姿态变化 °',180/Math.PI]]],['手指脱离与释放',[['gripper_opening_m','实际开口 mm',1000],['both_fingers_open_and_detached','双指实际脱离 0/1',1],['tcp_object_distance_m','TCP辅助距离 mm',1000]]],['接近、离架与持物搬运',[['grasp_approach_position_error_m','抓取接近 mm',1000],['source_bottom_envelope_clearance_m','离架净空 mm',1000],['preinsert_distance_m','预插入距离 mm',1000]]]];
const colors=['#167d62','#a05936','#5678bc'];for(let [title,series] of specs){let card=el('section',undefined,'card');card.append(el('h2',title));let svg=base(215),all=[];series.forEach(([key,_,scale])=>R.forEach(r=>{let m=r.metrics[key];if(Number.isFinite(m))all.push(m*scale)}));let lo=all.length?Math.min(...all):0,hi=all.length?Math.max(...all):1;if(hi===lo){lo-=.5;hi+=.5}const y=v=>175-(v-lo)/(hi-lo)*140;
svg.append(svgEl('text',{x:0,y:40},fmt(hi)),svgEl('text',{x:0,y:175},fmt(lo)),svgEl('text',{x:90,y:202},fmt(min)+' s'),svgEl('text',{x:925,y:202},fmt(max)+' s'));
series.forEach(([key,label,scale],i)=>{let points='',segments=[],valid=0;for(let r of R){let m=r.metrics[key];if(Number.isFinite(m)){points+=(90+(r.t-min)/(max-min||1)*880).toFixed(2)+','+y(m*scale).toFixed(2)+' ';valid++}else if(points){segments.push(points);points=''}}if(points)segments.push(points);segments.forEach(p=>svg.append(svgEl('polyline',{points:p,fill:'none',stroke:colors[i%3],'stroke-width':1.6})));card.append(el('span',label+(valid?'':' · unknown'),'muted'),document.createTextNode('　'))});if(!all.length)svg.append(svgEl('text',{x:450,y:100},'unknown · 无可用证据'));card.append(svg);document.getElementById('charts').append(card)}
const eventBox=document.getElementById('events');for(let e of E){let row=el('div',undefined,'event'),b=el('button',fmt(e.t)+' s');b.onclick=()=>{seek.value=e.t;display(e.t)};row.append(b,el('span',e.name+' · candidate '+fmt(e.candidate_start_t)+' s · confirmed '+fmt(e.confirmed_t??e.t)+' s'));eventBox.append(row)}if(!E.length)eventBox.textContent='无已确认事件。';
document.getElementById('terminal').textContent=JSON.stringify({termination_domain:D.summary.termination_domain,unfinished_requirement:D.summary.unfinished_requirement,failure_observation:D.summary.failure_observation,original_labels:D.identity.original_labels},null,2);
document.getElementById('identity').textContent=JSON.stringify({identity:D.identity,evidence:D.evidence},null,2);
document.getElementById('recording').textContent=JSON.stringify({attempts:D.summary.attempts,recording:D.summary.recording,integrity:D.summary.output_integrity},null,2);display(min);
</script></html>'''
