"""Update the final offline gallery from measured evidence and coverage notes.

The current consolidated HTML is the reusable template/media container. No
historical HTML version is needed. New recordings are fully decoded before
embedding; existing recordings retain their bytes and original result labels.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html import escape
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def image_url(path):
    from PIL import Image

    stream = io.BytesIO()
    image = Image.open(path).convert("RGB")
    image.thumbnail((960, 720))
    image.save(stream, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode()


def encode_video(item, temporary, ffmpeg):
    path, relative = item
    key = hashlib.sha256(relative.encode()).hexdigest()[:14]
    encoded, poster = temporary / (key + ".mp4"), temporary / (key + ".jpg")
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0", "-an",
                    "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "24",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded)], check=True)
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(encoded), "-f", "null", "-"], check=True)
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-ss", "0", "-i", str(encoded),
                    "-frames:v", "1", "-vf", "scale=640:-2", "-update", "1", str(poster)], check=True)
    raw = encoded.read_bytes()
    metadata = {"path": relative, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "embedded_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    tag = '<script type="application/octet-stream" id="media-' + key + '">' + base64.b64encode(raw).decode() + '</script>'
    return key, metadata, image_url(poster), tag



def update_unit_status(page, index_path):
    """Refresh evidence-backed card status and filters without touching media."""
    index_path = Path(index_path)
    index = json.loads(index_path.read_text())
    # Keep unit summaries on the existing cards, without changing historical runs.
    pattern = r'(<script id="payload" type="application/json">)(.*?)(</script>)'
    match = re.search(pattern, page, re.S)
    payload = json.loads(match[2])
    for unit in index['units']:
        if 'card_update' not in unit:
            continue
        asset = next(a for a in payload['assets'] if a['id'] == unit['asset_id'])
        category = next(c for c in payload['categories'] if c['asset_key'] == asset['key'])
        category.update(unit['card_update'])
        if category.get('readiness') == 'interaction':
            expert = next(r for r in unit['runs'] if r['backend'] == 'Teacher')
            result = json.loads((index_path.parent / expert['folder'] / 'result.json').read_text())
            if not result['task_success']:
                raise ValueError('Verified card requires a successful expert result')
            asset['readiness'] = 'interaction'
            asset['validation_label'] = category['validation_label']
        asset.update(unit.get('asset_update', {}))
        asset['requirement_correspondence'].update(
            robot_scope=category['robot'], blocker=category['blocker'], next_step=category['next_step'])
    payload['coverage'] = [[c['category_id'], c['title'], c['mapping'], c['robot'], c['blocker']]
                           for c in payload['categories']]
    page = page[:match.start(2)] + compact(payload) + page[match.end(2):]
    metadata = re.search(r'(<script type="application/json" id="unit-validation-metadata">)(.*?)(</script>)', page, re.S)
    if metadata:
        value = json.loads(metadata[2])
        value['index'] = index
        page = page[:metadata.start(2)] + compact(value) + page[metadata.end(2):]
    page = page.replace("${a.attempt_run?'机械臂尝试未通过':label[a.readiness]}",
                        "${a.validation_label||(a.attempt_run?'机械臂尝试未通过':label[a.readiness])}")
    counts = {state: sum(c['readiness'] == state for c in payload['categories'])
              for state in ('interaction', 'kinematic', 'static', 'missing')}
    filters = {'interaction': ('机械臂流程已验证', counts['interaction'] + int('baseline-card-template' in page)),
               'kinematic': ('仅关节回放', counts['kinematic']),
               'static': ('静态主资产／交互未通过', counts['static']),
               'missing': ('整机未建成', counts['missing']),
               'pending': ('尚未通过机械臂验证', 9 - counts['interaction'])}
    for state, (label, count) in filters.items():
        page = re.sub(r'(<input type="radio" name="readiness" value="' + state + r'">)[^<]+',
                      lambda m: m[1] + f'{label} · {count}', page)
    page = re.sub(r'<strong>\d+</strong><span>已有机械操作的类别</span><small>.*?</small>',
                  f'<strong>{counts["interaction"]:02d}</strong><span>已有机械操作的类别</span>'
                  '<small>IKA · DIYNAFLUOR · Flex · MagSep · PCR 派生插管</small>', page)
    return page


def add_unit_validation(page, index_path, ffmpeg):
    """Embed current unit results inside each existing instrument inspector."""
    index_path = Path(index_path)
    index = json.loads(index_path.read_text())
    sections, media, expert_passed, policy_passed = [], [], 0, 0
    with tempfile.TemporaryDirectory(prefix="labsim-unit-media-") as directory:
        for unit in index["units"]:
            content = [f'<h3>{escape(unit["name"])}</h3><p>{escape(unit["goal"])}</p>',
                       '<p>Expert 任务成功、policy 动作连通与 policy 任务成功分别判定；全部为仿真，未进行训练或真机验证。</p>',
                       f'<pre>./labsim unit collect --unit {escape(unit["id"])} --headless --output outputs/unit_NEW\n'
                       f'./labsim unit eval --unit {escape(unit["id"])} --backend gpt6 --provider-config /path/provider.json --headless --output outputs/policy_NEW</pre>']
            for run in unit["runs"]:
                folder = index_path.parent / run['folder']
                result = json.loads((folder / 'result.json').read_text())
                if run['backend'] == 'Teacher':
                    expert_passed += int(result['task_success'])
                else:
                    policy_passed += int(result['task_success'])
                label = '任务完成' if result['task_success'] else '任务未完成'
                content.append(f'<details class="explain"><summary>{escape(run["backend"])} · {label} · {result["duration_s"]:.2f}s 仿真</summary>'
                               f'<p>{escape(run["scope"])}</p><p>结束原因：{escape(result["termination_reason"])}；物理步数：{result["steps"]}</p>')
                if (folder / 'pi05/summary.json').exists():
                    motion = json.loads((folder / 'pi05/summary.json').read_text())
                    content.append(f'<p>模型推理 {motion["actual_model_requests"]} 次；实际执行 {motion["executed_actions"]} 个动作；'
                                   f'末端累计路径 {motion.get("measured_tcp_path_m", 0)*100:.1f} cm，'
                                   f'相对起点最大位移 {motion.get("measured_tcp_max_excursion_m", 0)*100:.1f} cm。</p>')
                videos = [(view, folder / (view + '.mp4'), view)
                          for view in run.get('views', ['front', 'side'])]
                if run.get('show_initialization'):
                    content.append('<p><b>以下主录像仅为 π0.5 控制段。</b>初始抓取由独立 expert 完成，不计入模型动作、时长或能力；准备录像在下方单独列出。</p>')
                    videos.append(('initialization', folder / 'initialization/front.mp4', 'initialization'))
                for view, path, suffix in videos:
                    if view == 'initialization':
                        content.append('<details><summary>独立抓取准备录像 · Expert 初始化，非 π0.5</summary>')
                        title = 'Expert 抓取并移动至目标上方约 6 cm'
                    else:
                        title = {'front': '正面', 'side': '侧面', 'detail': '孔位／夹持特写'}[view]
                    key, record, poster, tag = encode_video((path, f'unit/{unit["id"]}/{run["backend"]}/{suffix}.mp4'), Path(directory), ffmpeg)
                    media.append(record)
                    content.append(f'<p>{title}</p><video controls playsinline preload="none" poster="{poster}" '
                                   f'data-unit-media="media-{key}" style="width:100%;background:#080808;border-radius:10px"></video>')
                    sections.append(tag)
                    if view == 'initialization':
                        content.append('</details>')
                content.append('<details><summary>独立判分</summary><pre>' + escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre></details></details>')
            sections.append(f'<template id="unit-{unit["asset_id"]}">' + ''.join(content) + '</template>')
    sections.append('<script type="application/json" id="unit-validation-metadata">' + compact(dict(index=index, videos=media)) + '</script>')
    sections.append(r'''<script>
function showUnitValidation(asset){
 let box=document.getElementById('detail-unit-validation');
 if(!box){box=document.createElement('section');box.id='detail-unit-validation';box.style.padding='24px';document.getElementById('asset-dialog').append(box)}
 box.querySelectorAll('video').forEach(v=>{v.pause();URL.revokeObjectURL(v.dataset.objectUrl)});
 const template=document.getElementById('unit-'+asset.id);box.replaceChildren();box.hidden=!template;
 if(template){box.append(template.content.cloneNode(true));box.querySelectorAll('video').forEach(video=>{
  const raw=atob(document.getElementById(video.dataset.unitMedia).textContent.trim());
  const url=URL.createObjectURL(new Blob([Uint8Array.from(raw,c=>c.charCodeAt(0))],{type:'video/mp4'}));
  video.src=url;video.dataset.objectUrl=url;video.addEventListener('play',()=>pauseOthers(video));
 })}
}
document.getElementById('asset-dialog').addEventListener('close',()=>{
 document.querySelectorAll('#detail-unit-validation video').forEach(v=>{v.pause();v.removeAttribute('src');v.load();URL.revokeObjectURL(v.dataset.objectUrl)})
});
document.getElementById('asset-grid').addEventListener('click',event=>{
 if(event.target.closest('[data-unit-link]'))document.getElementById('detail-unit-validation').scrollIntoView({block:'start'});
});
</script>''')
    page = update_unit_status(page, index_path)
    payload = json.loads(re.search(r'<script id="payload" type="application/json">(.*?)</script>', page, re.S)[1])
    notice = (f'<div class="notice unit-current-notice"><strong>{expert_passed} 个单细胞 unit expert 已完成；'
              f'当前所选 policy 任务成功 {policy_passed} 次。</strong><br>'
              'Flex／MagSep 新增实际放置尝试，抓取准备与 π0.5 控制分别展示。'
              'PCR 新增小试管插孔，孔腔和耗材为未标定工程派生模型。详见各资产卡片。</div>')
    page = re.sub(r'<div class="notice(?: unit-current-notice)?"><strong>(?:\d+ 类已有明确范围|\d+ 个单细胞 unit).*?</div>',
                  lambda _: notice, page, flags=re.S)
    page = page.replace('PCR 的源样品块／孔阵列是实心碰撞体，需可信孔腔与耗材几何；',
                        'PCR 原资产仍为实心块；新增插管 unit 使用未标定的工程派生孔腔和小管，已验证插入，厂家尺寸仍待确认；')
    video_count = len(payload['media']) + page.count('src="data:video/mp4;base64,') + len(media)
    page = re.sub(r'\d+ EMBEDDED VIDEOS', f'{video_count} EMBEDDED VIDEOS', page)
    page = re.sub(r'<!-- unit-validation:start -->.*?<!-- unit-validation:end -->\n?', '', page, flags=re.S)
    page = page.replace("detailView('front');$('asset-dialog').showModal();", "showUnitValidation(a);detailView('front');$('asset-dialog').showModal();") if 'showUnitValidation(a);detailView' not in page else page
    ids = compact([unit['asset_id'] for unit in index['units']])
    marker = '<!-- unit-card-link -->'
    page = re.sub(r'\n<!-- unit-card-link -->[^\n]*', '', page)
    anchor = '  <p class="robot-scope"><b>机械臂操作</b>${escapeHTML(c.robot)}</p>'
    page = page.replace(anchor, anchor + '\n' + marker + f'<p>${{{ids}.includes(a?.id)?`<button data-asset="${{a.key}}" data-unit-link>单细胞测序 unit · Expert / GPT / π0.5 验证 ↗</button>`:\'\'}}</p>')
    block = '<!-- unit-validation:start -->' + '\n'.join(sections) + '<!-- unit-validation:end -->'
    return page.replace('</body>', block + '\n</body>')


def add_baseline_section(page, definition_path, ffmpeg):
    """Add an original-instrument card and inspector to the shared asset grid."""
    root = Path(__file__).resolve().parents[1]
    definition = json.loads(definition_path.read_text())
    report_path = root / definition["report"]
    report = json.loads(report_path.read_text())
    records = {item["path"]: item for item in report["media"]}

    def verified_file(relative):
        path = report_path.parent / relative
        raw = path.read_bytes()
        record = records[relative]
        if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError(f"Baseline evidence differs from its original report: {path}")
        return path, raw

    overview, _ = verified_file(definition["overview"])
    primary = report["primary"]
    result = report["primary_result"]
    if not result["full_success"] or not result["stable_after_retreat"]:
        raise ValueError("Selected original episode is not a complete successful task")
    videos, metadata = [], []
    for index, item in enumerate(definition["videos"]):
        path, raw = verified_file(item["path"])
        poster, _ = verified_file(item["poster"])
        subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(path),
                        "-f", "null", "-"], check=True)
        encoded = base64.b64encode(raw).decode()
        videos.append(f'''<article class="explain"><h3>{escape(item['title'])}</h3>
<p>{escape(item['description'])}</p><video id="baseline-video-{index}" controls playsinline
preload="none" poster="{image_url(poster)}" aria-label="{escape(item['title'])}"
style="width:100%;margin-top:16px;background:#080808;border-radius:10px"
src="data:video/mp4;base64,{encoded}"></video></article>''')
        metadata.append({**item, "source_path": path.relative_to(root).as_posix(),
                         "sha256": records[item["path"]]["sha256"], "bytes": len(raw)})
    provenance = {"source_report": definition["report"],
                  "source_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                  "original_report_date": report["created_at"], "primary": primary,
                  "primary_result": result, "videos": metadata, "new_gpu_run": False,
                  "counted_in_new_asset_catalog": False}
    section = f'''<!-- baseline-showcase:start -->
<template id="baseline-card-template"><article class="card requirement-card" data-category="baseline">
<button class="card-image" data-baseline aria-label="查看原有比色皿装载仪器">
<img src="{image_url(overview)}" alt="原有比色皿装载仪器、来源架与 Franka" loading="lazy"><span class="format">CAD → USD</span></button>
<div class="card-body"><div class="category">原有资产 / LabSim 基线</div>
<h3>比色皿装载仪器</h3><span class="pill">历史机械臂流程已验证</span>
<p class="correspondence"><b>对应资产</b>原仪器及原 A/B 座，配套 6×6 来源架、比色皿和 Franka；厂家型号未确认。</p>
<p class="robot-scope"><b>机械臂操作</b>抓取、搬运、插入原 A 座、松爪、撤离并稳定观察 3 秒。</p>
<p class="blocker-note"><b>尚未覆盖／原因</b>盖板预先打开，未验证开关盖；无测量功能和真机验证。</p>
<p><button data-baseline>观看机械臂验证 ↗</button></p>
<div class="card-bottom"><span class="small">原有仪器 · 2 段历史录像</span><button data-baseline>查看资产 ↗</button></div>
</div></article></template>
<dialog id="baseline-dialog" aria-labelledby="baseline-title">
<div class="dialog-head"><div><div class="eyebrow" style="margin:0 0 4px;font-size:10px">Asset Inspector</div>
<h2 id="baseline-title">比色皿装载仪器 · 原有 LabSim 资产</h2></div>
<button class="dialog-close" id="close-baseline" aria-label="关闭原有仪器详情">×</button></div>
<div style="padding:24px">
<div class="explain-grid" style="grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))">
<div class="explain"><img src="{image_url(overview)}" alt="原有仪器、完整来源架与 Franka 的历史仿真场景"
style="width:100%;border-radius:10px"><h3>{escape(definition['title'])}</h3>
<p>来自原 LabSim 的供给 CAD／USD 及其派生场景，配套完整 6×6 来源架、比色皿和 Franka。
不是此次从 ChemLab 接入的新设备；没有可确认的厂家型号，不能据此外观替代九类清单中的缺失设备。</p>
<p><b>资产入口</b>：<code>assets/lab_cuvette_loading/V0_demo04/instrument_native.usda</code>；
演示使用 <code>cuvette_xy_1000</code> 与原 A 座 <code>candidate_far_hinge</code>。</p></div>
<div class="explain"><span class="pill">历史接触仿真 · 完整任务通过</span>
<h3>抓取 → 搬运 → 插入 → 松爪 → 撤离 → 稳定</h3>
<p>展示 2026-10-22 报告中的 Size_v1 原始运行，仿真时间 {primary['simulation_seconds']:.2f} 秒。
独立评分确认完整成功，撤离后稳定观察 3 秒。控制器使用器皿真值；不等同于 GPT 自主策略成功。</p>
<p><b>未覆盖</b>：盖板在此场景中已打开，未验证机械臂开关盖；没有光谱测量、液体过程或真机验证。
10×10×67.5 mm 器皿尺寸及质量、摩擦等包含工程假设，不能解释为原厂兼容或实测精度。</p>
<p>本轮只整理已有证据，没有新增 GPU 运行。原始警告与结果完整保留在下方证据说明。</p>
<a href="#baseline-videos">观看原有仪器操作 ↓</a></div></div>
<div id="baseline-videos" class="explain-grid" style="grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));margin-top:24px">
{''.join(videos)}</div><details><summary>原始运行、视频来源与验证边界</summary>
<pre>{escape(json.dumps(provenance, ensure_ascii=False, indent=2))}</pre></details></div></dialog>
<script>
function baselineVisible(){{
 const q=document.getElementById('search').value.trim().toLowerCase();
 const state=document.querySelector('input[name=readiness]:checked').value;
 const cat=document.getElementById('category-filter').value,source=document.getElementById('source-filter').value;
 return ['all','interaction'].includes(state)&&['all','baseline'].includes(cat)&&['all','baseline'].includes(source)&&
 document.getElementById('baseline-card-template').content.textContent.toLowerCase().includes(q);
}}
document.getElementById('asset-grid').addEventListener('click',event=>{{if(event.target.closest('[data-baseline]')){{
 document.querySelectorAll('video').forEach(video=>video.pause());
 const dialog=document.getElementById('baseline-dialog');dialog.showModal();dialog.scrollTop=0;
}}}});
document.getElementById('close-baseline').onclick=()=>document.getElementById('baseline-dialog').close();
document.getElementById('baseline-dialog').addEventListener('close',()=>document.querySelectorAll('#baseline-dialog video').forEach(video=>video.pause()));
document.querySelectorAll('#baseline-dialog video').forEach(active=>active.addEventListener('play',
()=>document.querySelectorAll('video').forEach(video=>{{if(video!==active)video.pause()}})));
</script>
<!-- baseline-showcase:end -->'''
    page = re.sub(r'<!-- baseline-showcase:start -->.*?<!-- baseline-showcase:end -->\s*', '', page, flags=re.S)
    page = page.replace('<dialog id="asset-dialog"', section + '\n<dialog id="asset-dialog"', 1)
    page = page.replace('<a href="#baseline">原有资产</a>', '')
    page = page.replace('<a href="#assets">新增九类</a>', '<a href="#assets">数字资产</a>')
    page = page.replace('九类设备与数字资产对应', '实验设备与数字资产总览')
    page = page.replace('严格按清单 01–09 排序。每类说明参考型号、实际替代资产、机械臂可用范围与补齐条件；问号表示整机尚未建成。',
                        '汇总九类清单设备与原有比色皿装载仪器。清单 01–09 保持原顺序，原有仪器列于其后；每张卡片说明资产来源、机械臂操作范围与未完成项。')
    page = page.replace('全部九类设备', '全部设备 · 10 项')
    page = page.replace('机械臂流程已验证 · 4', '机械臂流程已验证 · 5')
    page = page.replace('9 类设备 · 7 个注册项</span>', '9 类清单 + 1 套原有仪器</span>')
    page = page.replace('搜索九类设备、参考型号或实际资产', '搜索设备、参考型号或实际资产')
    page = page.replace('另列 1 套原有 LabSim 仪器', '另含 1 套原有 LabSim 仪器')
    if '<option value="baseline">原有比色皿装载仪器</option>' not in page:
        page = page.replace('<option value="all">全部类别</option>', '<option value="all">全部类别</option><option value="baseline">原有比色皿装载仪器</option>')
        page = page.replace('<option value="other">其他开源硬件</option>', '<option value="other">其他开源硬件</option><option value="baseline">原有 LabSim 资产</option>')
    page = page.replace("source==='all'||(a&&(source==='chemlab')", "source==='all'||(source!=='baseline'&&a&&(source==='chemlab')")
    page = re.sub(r'function renderAssets\(\)\{.*?\n\}', '''function renderAssets(){
 const list=filteredAssets(), original=baselineVisible();
 $('asset-count').textContent=(list.length+Number(original))+' / 10 项 · 9 类清单 + 1 套原有仪器';
 $('asset-grid').innerHTML=list.map(renderCategory).join('')+(original?$('baseline-card-template').innerHTML:'')||'<div class="empty">没有匹配项。请调整筛选或点击重置。</div>';
}''', page, flags=re.S)
    payload = json.loads(re.search(r'<script id="payload" type="application/json">(.*?)</script>', page, re.S)[1])
    total = len(payload["media"]) + len(videos)
    page = re.sub(r'\d+ EMBEDDED VIDEOS', f'{total} EMBEDDED VIDEOS', page)
    page = page.replace('<span>注册资产</span>', '<span>新增注册资产</span>')
    page = page.replace('3 台设备几何 + 4 项装配／架体', '另列 1 套原有 LabSim 仪器')
    return page


def update_gallery(base, evidence, output, coverage_path, baseline_path=None):
    """Refresh the nine-category gallery without changing old measured results."""
    import imageio_ffmpeg

    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    page = base.read_text()
    pattern = r'(<script id="payload" type="application/json">)(.*?)(</script>)'
    match = re.search(pattern, page, re.S)
    if match is None:
        raise ValueError("Base gallery has no payload")
    data = json.loads(match[2])
    if "categories" not in data:
        raise ValueError("Use the final nine-category gallery as --base")
    index = json.loads((evidence / "index.json").read_text())
    categories = json.loads(coverage_path.read_text())["categories"]
    if [c["category_id"] for c in categories] != list(range(1, 10)):
        raise ValueError("Coverage must contain categories 1–9 in order")
    items, additions = [], []
    for definition in index["runs"]:
        folder = (evidence.parent / definition["folder"]).resolve()
        if not folder.is_relative_to(evidence.resolve()):
            raise ValueError("Evidence folder escapes its package")
        result = json.loads((folder / "result.json").read_text())
        if result["success"] != definition["expected_success"]:
            raise ValueError("Run label disagrees with measured result")
        if result["success"] and (not result.get("checks") or not all(result["checks"].values())):
            raise ValueError("Successful run must pass every check")
        existing = next((r for r in data["runs"] if r["id"] == definition["id"]), None)
        if existing:
            if existing["result"] != result:
                raise ValueError("An existing run ID cannot replace its measured result")
            existing.update({k: definition[k] for k in ("title", "group", "description", "date", "folder")})
            continue
        views = {}
        for view in ("front", "side", "detail"):
            path = folder / (view + ".mp4")
            if path.is_file():
                relative = definition["folder"] + "/" + path.name
                views[view] = hashlib.sha256(relative.encode()).hexdigest()[:14]
                items.append((path, relative))
        if not {"front", "side"} <= views.keys():
            raise ValueError("Missing front/side recordings")
        additions.append({k: definition[k] for k in ("id", "title", "group", "description", "date", "folder")}
                         | {"kind": "robot", "views": views, "result": result,
                            "duration": result["duration_s"], "preferred_view": "front"})
    with tempfile.TemporaryDirectory(prefix="labsim-encode-") as temporary:
        with ThreadPoolExecutor(max_workers=2) as pool:
            encoded = list(pool.map(lambda item: encode_video(item, Path(temporary),
                imageio_ffmpeg.get_ffmpeg_exe()), items))
    for key, metadata, poster, _ in encoded:
        data["media"][key], data["posters"][key] = metadata, poster
    data["runs"] = additions + data["runs"]
    assets = {a["key"]: a for a in data["assets"]}
    for key, changes in index["asset_updates"].items():
        if "evidence" in assets[key]:
            assets[key]["source_preview_evidence"] = assets[key].pop("evidence")
        assets[key].update(changes)
        run = next(r for r in data["runs"] if r["id"] == changes.get("robot_run", changes.get("attempt_run")))
        assets[key]["current_validation"] = {
            "task": run["result"]["task"], "success": run["result"]["success"],
            "passed": sum(run["result"]["checks"].values()), "total": len(run["result"]["checks"]),
            "duration_s": run["duration"], "real_calibrated": False, "result_folder": run["folder"]}
        if "robot_run" in changes and not run["result"]["success"]:
            raise ValueError("A failed attempt cannot promote an asset to verified")
    for c in categories:
        a = assets.get(c["asset_key"])
        c["readiness"] = a["readiness"] if a else "missing"
        if a:
            if a["category_id"] != c["category_id"]:
                raise ValueError("Asset/category mismatch")
            c["robot_run"], c["attempt_run"] = a.get("robot_run"), a.get("attempt_run")
        for key in (c["asset_key"], c.get("auxiliary_asset_key")):
            if key:
                assets[key]["requirement_correspondence"] = {
                    "category_id": c["category_id"], "title": c["title"], "reference_model": c["reference_model"],
                    "mapping": c["mapping"], "auxiliary_only": key == c.get("auxiliary_asset_key"),
                    "robot_scope": c["robot"], "blocker": c["blocker"], "next_step": c["next_step"]}
    data["categories"] = categories
    data["coverage"] = [[c["category_id"], c["title"], c["mapping"], c["robot"], c["blocker"]] for c in categories]
    data["assets"].sort(key=lambda a: a["category_id"])
    data["layout_updated_at"] = index["updated_at"]
    data["extension"] = {"scope": index["summary"], "cpu_tests": index["cpu_tests"]}
    for run in data["runs"]:
        run["folder"] = "evidence/" + run["id"]
    for key, metadata in data["media"].items():
        # Logical package path; the actual media bytes live only inside HTML.
        run = next(r for r in data["runs"] if key in r["views"].values())
        view = next(v for v, media in run["views"].items() if media == key)
        metadata["path"] = run["folder"] + "/" + view + ".mp4 (embedded)"
    robot_runs = [r for r in data["runs"] if r["kind"] == "robot"]
    robot_count = sum(len(r["views"]) for r in robot_runs)
    data["robot_video_count"] = robot_count
    page = page[:match.start(2)] + compact(data) + page[match.end(2):]
    page = page.replace("<script>\n'use strict';", "\n".join(x[3] for x in encoded) + "\n<script>\n'use strict';", 1)
    # Stable text/element patterns work for the first refresh and later rebuilds.
    page = re.sub(r'\d+ EMBEDDED VIDEOS', f"{len(data['media'])} EMBEDDED VIDEOS", page)
    page = re.sub(r'\d+ RUNS / \d+ VIDEOS', f"{len(data['runs'])} RUNS / {len(data['media'])} VIDEOS", page)
    counts = {state: sum(c["readiness"] == state for c in categories) for state in ("interaction", "kinematic", "static", "missing")}
    filters = {"interaction": ("机械臂流程已验证", counts["interaction"]),
               "kinematic": ("仅关节回放", counts["kinematic"]),
               "static": ("静态主资产／交互未通过", counts["static"]),
               "missing": ("整机未建成", counts["missing"]),
               "pending": ("尚未通过机械臂验证", 9 - counts["interaction"])}
    for state, (label, count) in filters.items():
        page = re.sub(r'(<input type="radio" name="readiness" value="' + state + r'">)[^<]+',
                      lambda m: m[1] + f"{label} · {count}", page)
    for group, title in (("all", "全部录像"), ("最新验证", "当前验证"), ("历史成功", "过程录像"), ("失败对照", "失败对照"), ("机构回放", "机构回放")):
        count = sum(len(r["views"]) for r in data["runs"] if group == "all" or r["group"] == group)
        page = re.sub(r'(<button[^>]*data-group="' + group + r'"[^>]*>)[^<]+', lambda m: m[1] + f"{title} · {count}", page)
    page = re.sub(r'<strong>\d+</strong><span>(?:机械臂交互设备|已有机械操作的类别)</span><small>.*?</small>',
                  f'<strong>{counts["interaction"]:02d}</strong><span>已有机械操作的类别</span><small>IKA · DIYNAFLUOR · Flex · MagSep</small>', page)
    page = re.sub(r'<strong>\d+</strong><span>机械臂录像</span><small>.*?</small>',
                  f'<strong>{robot_count}</strong><span>机械臂录像</span><small>{len(robot_runs)} 次运行 · 含真实失败记录</small>', page)
    page = re.sub(r'(<a[^>]*id="hero-play">).*?(</a>)', r'\1▶ 观看架体装载与取回\2', page)
    page = re.sub(r'(<button class="shot" id="hero-shot" aria-label=")[^"]+', r'\1观看 MagSep 架体装载到 Flex 并取回', page)
    hero_path = evidence / "rack-loading/loaded_settle-front.png"
    hero_image = (image_url(hero_path) if hero_path.is_file() else
                  re.search(r'<button class="shot" id="hero-shot"[^>]*><img src="([^"]+)"', page)[1])
    page = re.sub(r'(<button class="shot" id="hero-shot"[^>]*><img src=")[^"]+(" alt=")[^"]+',
                  lambda m: m[1] + hero_image + m[2] + 'Franka 将 MagSep 架体放在 Flex D2 工位', page)
    page = re.sub(r'(<span class="shot-badge">).*?(</span>)', r'\1FRANKA × FLEX × MAGSEP / CONTACT VERIFIED\2', page)
    page = re.sub(r'(<div class="showcase-foot">).*?(</div></div></div><div class="stats">)',
                  r'\1<div><strong>抓取 → 工位放置 → 释放撤离 → 取回</strong><span>连续接触仿真 · 仅架体搬运与放置</span></div><span class="pill">32 / 32 通过</span>\2', page)
    page = page.replace('到<span>完整自动操作。</span>', '到<span>可验证的机械操作。</span>')
    page = page.replace('全部录像已内嵌。最新结果、历史版本与失败对照均保留', '全部录像已集中内嵌在此最终文件。当前验证、过程录像与失败对照均可查看')
    page = re.sub(r'<div class="notice"><strong>目前没有宣称.*?</div>',
                  '<div class="notice"><strong>4 类已有明确范围的机械臂操作，不代表 4 台仪器的全部实验功能自动化。</strong><br>IKA 开盖／装载／关盖；DIYNAFLUOR 取帽／停放／盖回；新增同一连续流程验证 MagSep 架体搬运和 Flex 工位放置／取回。OpenFlexure 尝试未通过；PCR 原资产之外另有工程派生孔腔插管 unit，详见卡片。其余三类整机仍缺。现有 Franka 沿用项目资产。</div>', page)
    page = re.sub(r'<details class="completion-summary">.*?</details>',
                  '<details class="completion-summary"><summary>剩余项目能否补齐？</summary><p>已复用现有架体和工位完成 Flex／MagSep 接触流程。MagSep 插管、DIYNAFLUOR 样品管装载仍需匹配耗材模型和尺寸依据。</p><p>OpenFlexure 原装夹爪接近时碰样品架或照明支座，抬高后未形成双指稳定夹持；需要经过尺寸验证的细指或专用夹具及对应路径。不能删除碰撞体来冒充通过。</p><p>PCR 的源样品块仍为实心碰撞体；新增 unit 的孔腔和小管为未标定工程派生模型，已验证插入，仍需核对厂家尺寸；液滴、微孔和片段分析仍缺符合要求的整机装配或机构资料。具体条件与来源见各卡片。</p></details>', page, flags=re.S)
    page = re.sub(r'(<details><summary>版本、证据与文件说明</summary><p[^>]*>).*?(</p>)',
                  lambda m: m[1] + index["summary"] + ' 原有录像保留原始实验日期和判定。本 HTML 集中包含全部图像、视频及结果元数据，旧版页面与重复文件已清理；必要执行记录集中在 evidence，来源材料集中在 references。源项目链接需要联网，视频可离线播放。' + m[2], page, flags=re.S)
    page = re.sub(r'最新 CPU 回归：[^\n<]+', '最新 CPU 回归：' + index["cpu_tests"], page)
    page = page.replace('conda activate labsim\n', 'conda activate labsim\n# 新增：MagSep 架体装载／取回（不含插管和移液）\npython -m demos.cell_assets.handling --offline --output /new/path/rack-loading\n') if 'python -m demos.cell_assets.handling' not in page else page
    # Add direct links from category cards to both verified and failed evidence.
    marker = '<div class="card-bottom">${a?'
    if 'data-evidence=' not in page:
        page = page.replace(marker, '''<p>${(c.robot_run||c.attempt_run)?`<button data-evidence="${c.robot_run||c.attempt_run}">${c.robot_run?'观看机械臂验证':'查看未通过的尝试'} ↗</button>`:''}</p>''' + marker)
        page = page.replace("if(b)openAsset(b.dataset.asset)});", "if(b)openAsset(b.dataset.asset);const v=e.target.closest('[data-evidence]');if(v)latest(v.dataset.evidence)});")
    page = re.sub(r"function latest\(id='[^']+'\)\{.*?\}\n", "function latest(id='rack-loading'){if($('asset-dialog').open)$('asset-dialog').close();const run=D.runs.find(r=>r.id===id);setGroup(run?.group||'all');selectRun(id);$('demos').scrollIntoView({block:'start'})}\n", page)
    page = page.replace("latest(detailAsset.robot_run)", "latest(detailAsset.robot_run||detailAsset.attempt_run)")
    page = page.replace("$('detail-robot').hidden=!a.robot_run;", "$('detail-robot').hidden=!(a.robot_run||a.attempt_run);")
    page = page.replace("'观看机械臂完整操作 ↗'", "'观看机械臂验证录像 ↗'")
    page = page.replace("const markers=current.result.task===", "const markers=current.result.task==='rack_load_unload'?{grasp:'抓取架体',lift:'抬升',place:'工位放置',loaded_settle:'松手后稳定',retrieve:'重新取出',returned_settle:'取回后稳定'}:current.result.task===") if "task==='rack_load_unload'?" not in page else page
    page = page.replace("['open_load_close','uncap_park_recap']", "['open_load_close','uncap_park_recap','rack_load_unload']")
    page = page.replace("renderAssets();renderRuns();selectRun('cap-cycle');", "renderAssets();renderRuns();selectRun('rack-loading');")
    page = page.replace('${label[a.readiness]}</span>', "${a.attempt_run?'机械臂尝试未通过':label[a.readiness]}</span>")
    page = page.replace("'<li>无可动关节；以静态结构纳入。</li>'", "(a.key==='magsep'?'<li>架体在 handling 演示中为独立动态刚体，由夹爪接触搬运，无附着关节；默认资产仍静态。</li>':'<li>无可动关节；默认以静态结构纳入。</li>')")
    if baseline_path is not None:
        page = add_baseline_section(page, baseline_path, imageio_ffmpeg.get_ffmpeg_exe())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(page)
    suffix = " plus original LabSim evidence" if baseline_path is not None else ""
    print(f"Wrote {output}: 9 categories, {len(data['runs'])} extension runs, {len(data['media'])} extension videos{suffix}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Current final nine-category HTML")
    parser.add_argument("--evidence", type=Path, required=True, help="Evidence directory containing index.json")
    parser.add_argument("--coverage", type=Path, default=Path(__file__).resolve().parents[1] / "config/cell_assets/coverage.json")
    parser.add_argument("--output", type=Path, required=True, help="New single-file HTML; never overwritten")
    parser.add_argument("--baseline", type=Path, default=Path(__file__).resolve().parents[1] / "config/cell_assets/baseline_showcase.json",
                        help="Original LabSim evidence to display separately from the nine categories")
    parser.add_argument("--units", type=Path, help="Unit validation index; embed inside existing asset inspectors")
    args = parser.parse_args()
    update_gallery(args.base.resolve(), args.evidence.resolve(), args.output.resolve(), args.coverage.resolve(), args.baseline.resolve())
    if args.units:
        import imageio_ffmpeg
        page = add_unit_validation(args.output.read_text(), args.units, imageio_ffmpeg.get_ffmpeg_exe())
        args.output.write_text(page)


if __name__ == "__main__":
    main()
