"""Update the final offline gallery from measured evidence and coverage notes.

The current consolidated HTML is the reusable template/media container. No
historical HTML version is needed. New recordings are fully decoded before
embedding; existing recordings retain their bytes and original result labels.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
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
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-ss", "3", "-i", str(encoded),
                    "-frames:v", "1", "-vf", "scale=640:-2", "-update", "1", str(poster)], check=True)
    raw = encoded.read_bytes()
    metadata = {"path": relative, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "embedded_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    tag = '<script type="application/octet-stream" id="media-' + key + '">' + base64.b64encode(raw).decode() + '</script>'
    return key, metadata, image_url(poster), tag



def update_gallery(base, evidence, output, coverage_path):
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
                  '<div class="notice"><strong>4 类已有明确范围的机械臂操作，不代表 4 台仪器的全部实验功能自动化。</strong><br>IKA 开盖／装载／关盖；DIYNAFLUOR 取帽／停放／盖回；新增同一连续流程验证 MagSep 架体搬运和 Flex 工位放置／取回。OpenFlexure 尝试未通过，PCR 缺可插入结构。其余三类整机仍缺。现有 Franka 沿用项目资产。</div>', page)
    page = re.sub(r'<details class="completion-summary">.*?</details>',
                  '<details class="completion-summary"><summary>剩余项目能否补齐？</summary><p>已复用现有架体和工位完成 Flex／MagSep 接触流程。MagSep 插管、DIYNAFLUOR 样品管装载仍需匹配耗材模型和尺寸依据。</p><p>OpenFlexure 原装夹爪接近时碰样品架或照明支座，抬高后未形成双指稳定夹持；需要经过尺寸验证的细指或专用夹具及对应路径。不能删除碰撞体来冒充通过。</p><p>PCR 的源样品块／孔阵列是实心碰撞体，需可信孔腔与耗材几何；液滴、微孔和片段分析仍缺符合要求的整机装配或机构资料。具体条件与来源见各卡片。</p></details>', page, flags=re.S)
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
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(page)
    print(f"Wrote {output}: 9 categories, {len(data['runs'])} runs, {len(data['media'])} videos")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Current final nine-category HTML")
    parser.add_argument("--evidence", type=Path, required=True, help="Evidence directory containing index.json")
    parser.add_argument("--coverage", type=Path, default=Path(__file__).resolve().parents[1] / "config/cell_assets/coverage.json")
    parser.add_argument("--output", type=Path, required=True, help="New single-file HTML; never overwritten")
    args = parser.parse_args()
    update_gallery(args.base.resolve(), args.evidence.resolve(), args.output.resolve(), args.coverage.resolve())


if __name__ == "__main__":
    main()
