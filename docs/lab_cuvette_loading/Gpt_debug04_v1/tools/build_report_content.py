"""Build source-backed report JSON/Markdown for the restored debug04 trial.

This is a CPU-only content preparation tool. It does not author a DOCX, invoke
an artifact marker, read credentials, run a simulator or call a model. The
existing Policy_eval_v1/tools/build_report.py owns DOCX authoring and visual QA.
Historical reanalysis and the separately authorized current trial retain
different denominators. A closed formal run and complete analysis are required.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[4]
HISTORICAL_ID = '28bd2fc2-7bd7-44ee-9fb6-aaff53cbc99d'
STAGES = ('approach_grasp', 'grasp', 'extract', 'held_transport_50mm',
          'transport', 'align', 'insert', 'support_transfer', 'released',
          'retreated', 'stable_complete')
STAGE_CN = dict(approach_grasp='接近抓取', grasp='双指抓持', extract='离架',
    held_transport_50mm='持物横移50毫米', transport='预插入区域', align='对准',
    insert='有效插入', support_transfer='承托交接', released='合法释放确认',
    retreated='合格撤离确认', stable_complete='装载稳定完成')


def load(path):
    def invalid(value):
        raise ValueError(f'Non-finite JSON at {path}: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=invalid)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def num(value, digits=3, scale=1):
    if value is None:
        return 'N/A'
    value = float(value) * scale
    if not math.isfinite(value):
        raise ValueError('Use explicit missingness instead of a non-finite value')
    return f'{value:.{digits}f}'


def yes(value):
    return 'N/A' if value is None else ('是' if value else '否')


def stage_label(value):
    if value is None:
        return 'N/A'
    if value in ('none', 'not_started', 'unachieved'):
        return '无已确认阶段'
    return STAGE_CN.get(value, value)


def para(text):
    return dict(type='paragraph', text=text)


def table(headers, rows, widths):
    return dict(type='table', headers=headers, rows=rows, widths_cm=widths)


def image(path, caption, *, cap=8.0, width=16.4):
    return dict(type='image', path=path, caption=caption,
                width_cm=width, height_cap_cm=cap)


def page(title, *blocks):
    return dict(title=title, blocks=list(blocks))


def process_exit_path(run, episode):
    for path in (run/'process_exit.json', episode.parent/'process_exit.json'):
        if path.is_file():
            return path
    raise FileNotFoundError('Formal process_exit.json missing under run or environment')


def close_check(run, episode):
    """Never inspect a live writer or use partial formal results as complete."""
    proof = process_exit_path(run, episode)
    value = load(proof)
    if value.get('exited', value.get('process_exited')) is not True:
        raise ValueError('Formal native process is not declared closed')
    # Match the existing receipts, which may omit pid but always record exit.
    pid = value.get('native_pid', value.get('pid'))
    if pid is not None and Path(f'/proc/{int(pid)}').exists():
        raise ValueError('Formal process PID still exists; wait for owner audit')
    for child in value.get('children', []):
        if child.get('process_exited') is not True or child.get('native_pid_gone') is not True:
            raise ValueError('Child process does not have a closed native receipt')
        if child.get('pid') is not None and Path(f'/proc/{int(child["pid"])}').exists():
            raise ValueError('Formal child PID still exists')
    for name in ('result.json', 'progress_summary.json',
                 'recording_closed_receipt.json', 'project_scene_contract.json'):
        if not (episode / name).is_file():
            raise FileNotFoundError(episode / name)
    result = load(episode / 'result.json')
    if result.get('complete') is not True:
        raise ValueError('Formal result does not have complete=true')
    return value, result


def episode_metric(path, episode_id=None, *, formal=False):
    value = load(path)
    rows = value.get('episodes', []) if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError('Metrics must contain an episode list')
    selected = [row for row in rows
                if (episode_id is None or row.get('episode_id') == episode_id)
                and (not formal or row.get('purpose') == 'formal')]
    if len(selected) != 1:
        raise ValueError(f'Expected one separately identified episode, found {len(selected)}')
    return selected[0]


def stage_rows(historical, current):
    rows = []
    for name in STAGES:
        left = historical.get('stage_results', {}).get(name, {})
        right = current.get('stage_results', {}).get(name, {})
        rows.append([STAGE_CN[name], yes(left.get('reached')),
            num(left.get('first_confirmed_t')), yes(right.get('reached')),
            num(right.get('first_confirmed_t'))])
    return rows


def current_stats(current):
    """Report applicability-preserving quantities; never turn null into zero."""
    cont = current.get('continuous', {})
    rows = []
    for key, label, scale, unit in [
        ('target_lateral_error_m', '目标区横向误差', 1000, 'mm'),
        ('target_tilt_rad', '目标区倾角', 1, 'rad'),
        ('target_yaw_error_rad', '目标区方位误差', 1, 'rad')]:
        stat = cont.get('target_error_within_episode', {}).get(key, {})
        rows.append([label, stat.get('n', 'N/A'), num(stat.get('minimum'), 6, scale),
                     num(stat.get('mean'), 6, scale), unit])
    maximum = cont.get('maximum', {})
    rows += [
        ['有效插入深度', cont.get('insertion_applicable_sample_count', 'N/A'),
         num(maximum.get('valid_insertion_depth_m', {}).get('value'), 3, 1000),
         '适用区内最大值', 'mm'],
        ['释放后稳定时长', cont.get('post_release_sample_count', 'N/A'),
         num(maximum.get('post_release_stable_duration_s', {}).get('value')),
         cont.get('post_release_stable_duration_status', 'unknown'), 's']]
    return rows


def drift_rows(metric):
    rows = []
    for interval, records in metric.get('drift_intervals', {}).items():
        if interval not in ('operation', 'before_first_target_support', 'support_transfer'):
            continue
        for record in records:
            rows.append([record.get('attempt_id'),
                dict(operation='整个操作', before_first_target_support='首次支撑前',
                     support_transfer='支撑交接').get(interval, interval),
                record.get('valid_sample_count', 'N/A'),
                num(record.get('maximum_relative_translation_m'), 3, 1000),
                num(record.get('maximum_relative_rotation_rad'), 6)])
    return rows or [['N/A', '未建立固定抓持参考', 'N/A', 'N/A', 'N/A']]


def cost_for(ledger, episode_id):
    prefix = f'policy:{episode_id}:'
    rows = [row for row in ledger['attempts'] if row.get('label', '').startswith(prefix)]
    if not rows:
        raise ValueError('No ledger attempts with the exact formal episode prefix')
    return dict(attempts=len(rows), retries=sum(row.get('retry_index', 0) > 0 for row in rows),
        estimated_usd=sum(row['charged_estimate_usd'] for row in rows),
        input_tokens=sum(row.get('usage', {}).get('input_tokens', 0) for row in rows),
        output_tokens=sum(row.get('usage', {}).get('output_tokens', 0) for row in rows),
        http_seconds=sum(row.get('wall_seconds', 0) for row in rows),
        exact_label_prefix=prefix)


def media_inputs(evidence, current_media):
    historical = evidence / 'media/historical_debug04/media_receipt.json'
    receipts = []
    for case, receipt in [('historical_debug04', historical), ('debug04_01', current_media)]:
        value = load(receipt)
        if value.get('episode_id') is None:
            raise ValueError('Media receipt needs episode identity')
        video = value.get('full_dual_video', value.get('full_dual'))
        if not isinstance(video, dict) or 'path' not in video:
            raise ValueError('Media receipt needs a full continuous dual video')
        video_path = receipt.parent/video['path']
        if not video_path.is_file() or sha(video_path) != video['display_sha256']:
            raise ValueError('Full dual video missing or SHA mismatch')
        screenshots = value.get('screenshots', value.get('frames', []))
        checked = []
        for record in screenshots:
            p = receipt.parent / record['path']
            if not p.is_file():
                raise FileNotFoundError(p)
            expected = record.get('sha256')
            if expected and sha(p) != expected:
                raise ValueError('Screenshot SHA mismatch: ' + str(p))
            checked.append(dict(record, evidence_path='evidence:' + str(p.relative_to(evidence))))
        receipts.append(dict(case=case, receipt=receipt, data=value, screenshots=checked,
            video_relative_path=str(video_path.relative_to(evidence))))
    return receipts


def markdown(content):
    lines = ['# ' + content['title'], '', content.get('subtitle', ''), '']
    for page_value in content['pages']:
        lines += ['## ' + page_value['title'], '']
        for block in page_value['blocks']:
            kind = block['type']
            if kind in ('paragraph', 'heading'):
                lines += [str(block['text']), '']
            elif kind == 'table':
                lines += ['| ' + ' | '.join(map(str, block['headers'])) + ' |',
                          '| ' + ' | '.join('---' for _ in block['headers']) + ' |']
                lines += ['| ' + ' | '.join(str(v).replace('|', '\\|') for v in row) + ' |'
                          for row in block['rows']]
                lines.append('')
            elif kind == 'image':
                # Reading package B intentionally contains report files and
                # two continuous videos. DOCX embeds these real figures;
                # Markdown must not link to image files absent from that pack.
                lines += ['图：'+block.get('caption', '')+
                          '（已嵌入DOCX，原始图片与SHA见工程包A。）', '']
            elif kind == 'bullets':
                lines += ['- ' + str(value) for value in block['items']] + ['']
            elif kind == 'code':
                lines += ['```text', block['text'], '```', '']
    return '\n'.join(lines)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--formal-run', type=Path, required=True)
    p.add_argument('--formal-episode', type=Path, required=True)
    p.add_argument('--formal-metrics', type=Path, required=True)
    p.add_argument('--formal-media', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--authorization', type=Path, required=True)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--historical-metrics', type=Path)
    p.add_argument('--historical-quantification', type=Path)
    p.add_argument('--formal-quantification', type=Path)
    p.add_argument('--terminal-audit', type=Path)
    p.add_argument('--reader-summary', type=Path)
    p.add_argument('--validation', type=Path,
                   help='Optional finalized validation summary, never inferred from test intentions')
    p.add_argument('--formal-figure', action='append', default=[], type=Path,
                   help='Optional verified figure inside evidence-dir, in supplied order')
    p.add_argument('--output', type=Path, required=True,
                   help='New report content directory; existing paths are rejected')
    return p


def build(args):
    root, evidence, output = (p.resolve() for p in (args.root, args.evidence_dir, args.output))
    if output.exists():
        raise FileExistsError(output)
    run, ep = args.formal_run.resolve(), args.formal_episode.resolve()
    closed, result = close_check(run, ep)
    comparison_path = root/'docs/lab_cuvette_loading/Gpt_debug04_v1/environment_comparison.json'
    identity_path = root/'docs/lab_cuvette_loading/Gpt_debug04_v1/identity.json'
    comparison, identity = load(comparison_path), load(identity_path)
    historical_metrics = args.historical_metrics or evidence/'historical_metrics_01/episodes.json'
    historical_quantification = (args.historical_quantification or
        evidence/'historical_quantification_01/historical_quantification.json')
    formal_quantification = (args.formal_quantification or
        evidence/'new_quantification_01/quantification.json')
    historical = episode_metric(historical_metrics, HISTORICAL_ID)
    quantify = load(historical_quantification)
    current_quantify = load(formal_quantification)
    terminal_path = args.terminal_audit or evidence/'validation/terminal_contact_observation.json'
    terminal_audit = load(terminal_path)
    reader_path = args.reader_summary or root/'docs/lab_cuvette_loading/Gpt_debug04_v1/validation/official_reader_summary.json'
    reader = load(reader_path)
    if (reader.get('passed') is not True or reader.get('actual_batch_read') is not True
            or reader.get('source_hashes_unchanged') is not True
            or reader.get('source_labels_unchanged') is not True):
        raise ValueError('Official reader batch and source preservation have not passed')
    checks = {name: load(evidence/'validation'/filename) for name, filename in (
        ('closure', 'formal_debug04_01_closed.json'), ('identity', 'formal_identity_01.json'),
        ('schema', 'formal_schema_01.json'), ('drift', 'formal_drift_01.json'))}
    if any(value.get('passed') is not True for value in checks.values()):
        raise ValueError('Formal closure/identity/schema/drift checks must pass')
    current = episode_metric(args.formal_metrics, result['episode_id'], formal=True)
    if current.get('record_complete') is not True or current.get('analysis_evidence_valid') is not True:
        raise ValueError('Formal analysis has not verified complete evidence')
    if result['episode_id'] == HISTORICAL_ID:
        raise ValueError('New formal trial must not reuse historical episode identity')
    if current_quantify['episode_id'] != result['episode_id']:
        raise ValueError('Formal quantification has a different episode identity')
    if terminal_audit['episode_id'] != result['episode_id']:
        raise ValueError('Terminal physics audit has a different episode identity')
    if reader['episode_id'] != result['episode_id']:
        raise ValueError('Official reader summary has a different episode identity')
    provider = identity['frozen_policy']['profile_snapshot']
    protocol, authorization, ledger = map(load, (args.protocol, args.authorization, args.ledger))
    if authorization.get('approved') is not True or authorization.get('maximum_formal_episodes') != 1:
        raise ValueError('This report is scoped to the explicitly authorized single trial')
    original_ledger_path = root/comparison['cost_and_budget']['old_ledger']['path']
    original_ledger = load(original_ledger_path)
    if sha(original_ledger_path) != comparison['cost_and_budget']['old_ledger']['sha256']:
        raise ValueError('Protected historical ledger changed')
    if ledger['attempts'][:len(original_ledger['attempts'])] != original_ledger['attempts']:
        raise ValueError('Authorized cumulative ledger lost or changed historical prefix')
    newcost = cost_for(ledger, result['episode_id'])
    oldcost = comparison['cost_and_budget']
    current_gpt = load(ep/'gpt_control/summary.json')
    media = media_inputs(evidence, args.formal_media.resolve())
    if media[1]['data']['episode_id'] != result['episode_id']:
        raise ValueError('Formal media does not belong to the current episode')
    oldresult = identity['real_historical_result']
    actual_version = current.get('actual_execution_commit') or closed.get('runtime_commit')
    physics = comparison['physical_baseline_equivalence']
    runtime_config = load(ep/'project_scene_contract.json')
    facts = dict(historical_episode_id=HISTORICAL_ID, formal_episode_id=result['episode_id'],
        historical_denominator=0, historical_records_described=1, formal_authorized=1,
        formal_started=1, formal_complete=int(current['record_complete']),
        formal_valid=int(current['record_valid']), formal_task_evaluable=int(current['task_evaluable']),
        formal_success=int(current['task_success']), formal_runtime_commit=actual_version,
        historical_policy_estimated_usd=oldcost['historical_estimated_total_usd'],
        formal_policy_estimated_usd=newcost['estimated_usd'])
    def event_t(metric, name):
        return metric.get('stage_results', {}).get(name, {}).get('first_confirmed_t')
    def last_frame(records):
        match = next((r for r in records if r.get('label') == 'terminal'), None)
        return match or (records[-1] if records else None)
    def pick_frame(records, label):
        return next((r for r in records if r.get('label') == label), None)
    def shot(record, caption):
        return image(record['evidence_path'], caption +
            f' 实际帧{record.get("source_frame_index_zero_based", record.get("frame_index_zero_based", "N/A"))}，仿真'
            f'{num(record.get("actual_frame_simulation_s", record.get("actual_frame_simulation_time_s")))}秒。', cap=6.0)
    hfig = evidence/'media/historical_figures_02'
    figures = [hfig/'01_historical_first_times.png', hfig/'02_historical_progress_drift.png',
               hfig/'03_historical_applicable_errors.png']
    for p in [*figures, *args.formal_figure]:
        if not p.resolve().is_relative_to(evidence) or not p.is_file():
            raise ValueError('Figure must exist within evidence-dir: ' + str(p))
    hist_attempt_rows = [[row['attempt_id'], num(row['start_t']), num(row.get('end_t')),
        row.get('outcome'), row.get('ended_by')] for row in quantify['attempts']]
    milestones = stage_rows(historical, current)
    snapshots = []
    for record, caption in [
        (pick_frame(media[0]['screenshots'], 'first_preinsert'), '历史到达预插入区域'),
        (pick_frame(media[0]['screenshots'], 'first_quality_warning'), '历史首次抓持质量警告附近'),
        (last_frame(media[1]['screenshots']), '本轮正式单集终态')]:
        if record:
            snapshots.append(shot(record, caption))
    if not snapshots:
        raise ValueError('At least one actual screenshot is required')
    current_result_text = ('完整装载成功' if current['task_success'] else
        f'未完成完整装载，终止为{current.get("termination_reason")}，失败类别为{current.get("failure_type")}')
    pages = [
        page('结论与本轮实际范围',
            para(f'本报告复核原gpt_debug_04，并在当前Project_release_v1 standard环境恢复其冻结策略，'
                 f'实际执行1条新的正式轨迹。本轮{current_result_text}。历史记录和本轮复测分别说明，'
                 '历史离线分析不增加新实验分母；π0.5本轮没有重跑。'),
            table(['范围', '历史debug04', '本轮恢复单集'], [
                ['用途', '只读重分析，不计正式分母', 'policy_evaluation'],
                ['授权 / 实际启动', '历史既有1条', '1 / 1'],
                ['完整记录 / 记录有效', yes(historical['record_complete'])+' / '+yes(historical['record_valid']),
                 yes(current['record_complete'])+' / '+yes(current['record_valid'])],
                ['完整任务成功', yes(historical['task_success']), yes(current['task_success'])],
                ['最远确认阶段', stage_label(historical.get('farthest_stage')),
                 stage_label(current.get('farthest_stage'))],
                ['终止原因', historical.get('termination_reason'), current.get('termination_reason')],
                ['仿真时长 s', num(historical.get('simulation_seconds')), num(current.get('simulation_seconds'))],
            ], [4.0, 6.2, 6.2]),
            para('原模板预留10条试验槽位，本次付费授权只覆盖其中1条。这里不给出10次成功率，也不将历史记录与新单集合并估计泛化能力。'
                 '同样初态也不保证供应商返回相同决策：策略没有发送temperature或模型seed，后端权重身份和服务随机性无法独立核查。'),
            para('任务仍要求真实抓持、离架、搬运、原A座装载、支撑交接、实际释放与撤离后3秒稳定。'
                 '接近目标、TCP下降或夹持状态下的稳定都不单独构成完整成功。')),
        page('恢复的策略身份与模型输入',
            para('本轮恢复的是原gpt_debug_04的context4 640 high profile及完整历史vendor，'
                 '不是此前P9时序图像策略。原历史源提交与冻结源码逐字可追溯。'),
            table(['项目', '冻结设置'], [
                ['模型与API', provider['model']+'；HTTPS /v1/'+provider['endpoint']],
                ['工具', 'observe / move_ee / gripper / wait / finish'],
                ['输入图像', '原生640×480 RGB；Pillow LANCZOS最大边640，JPEG quality60，high detail'],
                ['上下文', '最近两个完整response与tool-receipt回合；每集重新建立history'],
                ['推理与输出', provider['reasoning_effort']+'；最多'+str(provider['max_output_tokens'])+'输出tokens'],
                ['时限', '单请求120秒；单集1800策略墙钟秒；最多160逻辑决策'],
                ['信息范围', '公开RGB、机器人/TCP/关节、触觉、相机标定、时间和静态任务文本'],
            ], [4.0, 12.4]),
            para('静态任务文本包含10×10×67.5 mm尺寸假设、A1/F6、内部A座、27 mm目标深度及hand到TCP标定。'
                 '模型没有器皿动态真值、孔口误差、Teacher路线、Progress、scorer或reward输入；finish只是终止并请求独立评分。'),
            para('原provider文件和vendor源保留；实际client通过独立财务覆层采用获批累计账本的金额与请求上限。'
                 '只有max_estimated_usd和max_requests两项财务字段允许改变，推理、图像、工具和动作限制不随预算调整。'),
            para('原配置SHA256 '+identity['frozen_policy']['profile_sha256']+'；原SYSTEM_PROMPT SHA256 '+
                 identity['frozen_policy']['SYSTEM_PROMPT_sha256']+'。完整tool schema与实际instructions重建SHA见身份JSON。')),
        page('物理环境与兼容桥核查',
            para('历史debug04与已闭合的发布版基线证据中，15组物理与执行配置在归一化缓存目录后相同，'
                 '7个契约资产实际文件SHA一致，真实初始化的器皿/TCP/关节状态逐值一致。'
                 '本轮正式单集的配置和初态另保存在新episode中，由最终核查绑定。'
                 '17个基础依赖有16个源码不变，唯一Teacher v6到v7支撑卸载改动不在GPT分支实例化。'),
            table(['模块', '保留的当前基线'], [
                ['场景', '完整白色6×6架；A1取物、F6蓝色邻物；单台yaw90°仪器与内部原A座'],
                ['器皿', 'cuvette_xy_1000，10×10×67.5 mm尺寸假设；20 g工程质量；28块有厚度碰撞'],
                ['座与目标', '原candidate_far_hinge，声明12.6 mm限制宽；27 mm目标深度；未更换适配座'],
                ['物理', '240 Hz，控制60 Hz；TGS 64/1，CCD；contact offset50 μm，rest offset0'],
                ['成功判据', '独立实际状态；释放与撤离后稳定3秒，漂移0.2 mm、姿态1°、观察穿透50 μm'],
                ['相机和动作', '原双640×480相机安装；同连续IK、contact_hold.v2、跟踪补偿与安全检查'],
            ], [3.4, 13.0]),
            para('新增launcher的可选client/runner/profile identity注入桥，用于接入完整历史vendor；默认原调用路径保留。'
                 '身份写入launch/run manifest，不写入场景配置。发布事务关闭、用途字段与Progress诊断旁路保留，'
                 '场景指纹包装不同不等于物理变化。'),
            para('28个输入碰撞块的烹饪响应与原座1350射线/1112命中结果一致。观察表面距离13.589/14.032 μm仅为有限样本；'
                 '尚无完整附着PxShape读回，也没有真实几何、质量或机器人动力学校准。')),
        page('历史轨迹的阶段证据',
            para(f'历史UUID {HISTORICAL_ID}，源运行提交{quantify["source_runtime_commit"]}。'
                 f'仿真{num(quantify["simulation_seconds"])}秒，{int(quantify["control_steps"])}控制步，'
                 f'{quantify["physical_samples"]}物理样本。原任务标签GRASP_SLIP保留；Progress离线重分析只补充证据。'),
            image('evidence:media/historical_figures_02/01_historical_first_times.png',
                  '完整事件流的首次阶段确认；未完成阶段保持N/A，不填零秒。', cap=7.0),
            table(['历史事件', '首次确认 s', '含义'], [
                ['双侧抓持', num(event_t(historical, 'grasp')), '实际接触候选持续确认'],
                ['来源槽清出', num(event_t(historical, 'extract')), '真实底面越过架口'],
                ['持物横移50毫米', num(event_t(historical, 'held_transport_50mm')), '部分搬运证据'],
                ['预插入区域', num(event_t(historical, 'transport')), '固定目标区域，不等于对准'],
                ['有效插入 / 支撑 / 释放', 'N/A', '未确认'],
            ], [4.6, 2.8, 9.0]),
            para('原结果最终grasp_success与transport_success仍为false；中间已发生的离架和横移事件不能改写原完整资格。'
                 '原任务retry_count与Progress物理attempt/retry为不同定义，后文分别列示。')),
        page('历史连续进度与抓持失稳',
            image('evidence:media/historical_figures_02/02_historical_progress_drift.png',
                  '真实控制端点Progress与相对运动；抓持质量警告和实际失持时刻分别标出。', cap=10.0),
            table(['尝试', '开始 s', '结束 s', '物理结果', '结束依据'], hist_attempt_rows,
                  [1.0, 2.2, 2.2, 2.0, 9.0]),
            para('历史首次抓持质量不满足发生于'+num(quantify['observed_control_times']['first_grasp_quality_false_t'])+
                 '秒，首次实际失持观察为'+num(quantify['observed_control_times']['first_actual_grasp_loss_observed_t'])+
                 '秒。两者不是同一事件；attempt内相对运动不按质量过滤，保留全部真实物理样本。'),
            para('历史有效插入进度最大为0，但适用插入深度、支撑交接和释放后稳定时长均为N/A。'
                 '旧legacy raw insert曾达到1，仅为未施加当前门控的诊断信号，不能当作有效插入。')),
        page('本轮正式单集的实际结果',
            para('当前完整UUID '+result['episode_id']+'；执行提交 '+str(actual_version)+'。'
                 '独立任务结果为 '+str(current['task_success'])+'，record_valid='+str(current['record_valid'])+
                 '，终止 '+str(current.get('termination_reason'))+'，失败 '+str(current.get('failure_type'))+'。'),
            table(['阶段', '历史达到', '历史首次 s', '新单集达到', '新单集首次 s'], milestones,
                  [4.5, 2.2, 2.7, 2.8, 4.2]),
            para('表中阶段由完整Progress事件流和物理观察确认，未用模型自述、动作目标或Teacher phase打标签。'
                 '新单集只有一个样本，逐项列真实结果，不对历史与本轮差值作统计显著性或整体优劣判断。'),
            para('BLOCKED是原scorer的通用任务类别；仅凭这个标签无法定位为腔内或座口插入受阻。'
                 '具体执行到哪里，以本表的物理确认事件与连续视频为准。'),
            para('新轨迹的post_retreat_window状态为 '+str(current.get('post_retreat_window', {}).get('status'))+
                 '，释放后稳定结果为 '+str(result.get('stable_after_retreat'))+'。若撤离未发生，该窗口保持unavailable/null，'
                 '中止前的末尾窗口只称terminal_window。'),
            para('实际动作执行数 '+num(current.get('resource', {}).get('executed_actions'), 0)+
                 '，拒绝数 '+num(current.get('resource', {}).get('action_rejections'), 0)+
                 '，裁剪数 '+num(current.get('resource', {}).get('action_clipped'), 0)+
                 '。残余物理质量告警：'+', '.join(result.get('physics_quality_flags', []))+ '。')),
        page('本轮连续量与适用区间',
            table(['量', '适用样本 n', '最小或最大值', '均值或状态', '单位'],
                  current_stats(current), [4.4, 2.1, 3.0, 5.3, 1.6]),
            para('目标误差只在entrance_region与current_attempt_route同时成立的控制端点统计。'
                 '不同误差最小值来自不同时间，不能拼成一个同时达成的理想姿态。未进入适用区间的量保持N/A。'),
            table(['尝试', '相对运动区间', '物理样本 n', '最大平移 mm', '最大转角 rad'],
                  drift_rows(current), [1.0, 5.3, 2.5, 3.9, 3.7]),
            para('相对运动使用每个attempt固定参考和240 Hz物理样本；不以控制频率最大值替代，不过滤抓持质量不佳样本。'
                 '支撑交接导致的相对运动需结合接触和状态解释，不能一概当抓持失败。')),
        page('连续视频与关键真实画面',
            para('每条完整视频对应同一次连续运行；两相机展示和时间映射由源video_timestamps绑定。'
                 '历史与新单集视频分别存放，未拼接、插帧或合成动作。'),
            *snapshots,
            para('阅读包B内完整录像：media/historical_debug04_dual.mp4；media/formal_debug04_01_dual.mp4。'
                 '便携Progress HTML附带全step、事件、summary/config与两相机播放副本。')),
        page('调用费用与授权上限',
            table(['资源', '历史原轨迹', '本轮正式单集'], [
                ['逻辑模型决策', oldresult['api_decisions'], current_gpt.get('api_decisions', current_gpt.get('api_calls'))],
                ['网络尝试 / 重试', str(oldcost['historical_network_attempts'])+' / '+str(oldcost['historical_retry_attempts']),
                 str(newcost['attempts'])+' / '+str(newcost['retries'])],
                ['输入 / 输出tokens', str(oldcost['historical_usage_input_tokens'])+' / '+str(oldcost['historical_usage_output_tokens']),
                 str(newcost['input_tokens'])+' / '+str(newcost['output_tokens'])],
                ['策略墙钟 s', num(oldresult['policy_wall_seconds']), num(current_gpt.get('wall_seconds'))],
                ['仿真时长 s', num(historical.get('simulation_seconds')), num(current.get('simulation_seconds'))],
                ['HTTP累计耗时 s', num(sum(row.get('wall_seconds', 0) for row in original_ledger['attempts']
                    if row.get('label', '').startswith('policy:'+HISTORICAL_ID+':'))), num(newcost['http_seconds'])],
                ['usage估算 USD', num(oldcost['historical_estimated_total_usd'], 6), num(newcost['estimated_usd'], 6)],
            ], [4.4, 6.0, 6.0]),
            para('用户本次明确授权额外USD20、最多480次网络尝试、只运行1集；新累计封顶USD49.267746/857网络次。'
                 '原377次/USD29.267746账本完整只读，新账本保留其完整前缀。模板中的其余9条未获本次授权，不列为已运行。'),
            para('按冻结2026-10-26配置估算输入$10/M、输出$50/M、缓存输入$1/M，供应商实际账单与账户倍率未知。'
                 '按原51次均值外推160次约$13.098，但保守单次80k输入+1024输出预留可达$0.8512，'
                 '$20并不数学保证160次含重试全部完成。每次请求前核查预留，预算不足即停。'),
            para('本轮关闭后累计估算USD'+num(ledger['total_estimated_usd'], 6)+'、网络'+str(ledger['total_network_attempts'])+
                 '次；按精确episode标签前缀区分此次成本与历史离线QA，不将原UUID下额外QA请求混入原51次。'),
            table(['本轮时间范围', '秒'], [
                ['策略循环墙钟', num(current_gpt.get('wall_seconds'))],
                ['原生run阶段 app启动后至shutdown前', num(closed.get('wall_seconds'))],
                ['app启动', num(closed.get('native_startup_seconds'))],
                ['app关闭', num(closed.get('native_shutdown_seconds'))],
                ['测量组件合计 不是整进程精确计时', num(closed.get('sum_measured_native_components_seconds'))],
                ['独立整进程墙钟', num(closed.get('whole_process_wall_seconds'))],
            ], [12.0, 4.4]),
            para('外层wrapper没有独立起点计时，整进程墙钟为N/A。组件合计不包含所有几何审计与父进程开销，'
                 '不通过文件时间戳相减伪造整进程测量。')),
        page('数据完整性与后续使用',
            para('当前结果、双视角录像、H5、Progress与关闭凭据均来自闭合单集，分析记录身份为 '+
                 current['episode_id']+'。成功BC资格为 '+str(result.get('success_bc_eligible'))+
                 '，失败分析资格为 '+str(result.get('trajectory_analysis_eligible'))+'，不为reader改变任务标签。'),
            table(['来源', '身份与用途'], [
                ['历史源执行提交', quantify['source_runtime_commit']],
                ['本轮正式执行提交', actual_version],
                ['内容生成时checkout', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()+
                 '（工作区有新分析源码）'],
                ['当前冻结场景指纹', runtime_config['frozen_scene_sha256']],
                ['原账本完整性', '原文件SHA与完整377项前缀保持；新累计账本独立授权'],
                ['本轮核查', '进程及记录关闭、profile身份、Progress schema、独立漂移与正式ACT/DP读取通过'],
            ], [4.2, 12.2]),
            para('复现先使用check-only核对源码与profile，正式付费执行须持单独授权文件和新输出路径。'
                 '当前run已消费一次授权，不应复制原授权反复启动。完整命令、冻结protocol和源码manifest随交付保存。'),
            dict(type='code', text='python -m demos.lab_cuvette_gpt_debug04_v1.run --check-only\n'
                 'python -m demos.lab_cuvette_policy_eval_v1.analysis --help'),
            para('本报告不重跑π0.5，不改动原座、物理、动作数值或独立评分规则。后续优先根据新单集失败阶段处理公开视觉对准、'
                 '抓持保持或插入策略；新增付费批次、策略输入变化和环境修改应分别冻结并重新授权。')),
    ]
    if args.formal_figure:
        # Optional original analysis figures replace prose space, without
        # changing metric values or synthesizing missing samples.
        for p in args.formal_figure[:1]:
            pages[6]['blocks'].insert(2, image('evidence:' + str(p.resolve().relative_to(evidence)),
                '本轮单集真实连续量；来源与SHA见源清单。', cap=4.7))
    if current_gpt.get('termination_reason') == 'POLICY_FINISH_REQUEST':
        pages[8]['blocks'].insert(1, para('本次由策略主动finish结束，没有触发本次USD20预算上限截断。'
            '该结束方式与此前P9评测的外部预算停止分别归类。完整任务结果仍由独立scorer给出。'))
    confirmed = [STAGE_CN[name] for name in STAGES
                 if current.get('stage_results', {}).get(name, {}).get('reached') is True]
    pages[5]['blocks'].insert(2, para('本轮已经物理确认：'+('、'.join(confirmed) or '无')+'。'
        '与历史结果逐阶段比较，不将中间动作等同于完整成功。'))
    terminal = terminal_audit['raw_terminal_physics']
    derived = terminal_audit['derived']
    window = terminal_audit['unchanged_original_windows']['terminal_window']
    pages[5]['blocks'].append(table(['终态诊断量', '实际值', '任务解释'], [
        ['双指开度与接触', num(derived['actual_total_finger_separation_m'], 3, 1000)+' mm；'+
         str(terminal['finger_contact_N'])+' N', '实际已经张爪且无双指接触；合法释放未确认'],
        ['目标底部间隙 / 原始深度', num(terminal['target_bottom_gap_m'], 4, 1000)+' / '+
         num(terminal['depth_m'], 6, 1000)+' mm', '原始终态几何诊断，不等于有效插入深度'],
        ['目标XY距离 / 容纳', num(derived['raw_terminal_target_xy_distance_m'], 4, 1000)+' mm / '+
         yes(terminal['target_region_contains_object']), '器皿在合法目标容纳区域之外'],
        ['入口接触 / 底部支撑', num(terminal['entrance_feature_contact_N'], 6)+' / '+
         num(terminal['target_bottom_support_N'], 3)+' N', '承重来自入口或壁体，未获目标底部承托'],
        ['整手净空', num(terminal['gripper_object_clearance_m'], 4, 1000)+' mm', '低于40 mm撤离门槛'],
        ['末尾窗口稳定', num(window['measured_duration_s'])+' s；漂移'+
         num(window['position_drift_m'], 7, 1000)+' mm', 'terminal_window；非释放撤离后的成功窗口'],
    ], [4.2, 5.1, 7.1]))
    pages[5]['blocks'].append(para('终帧器皿停在入口侧局部结构上，实际张爪不等于正确装载释放。'
        '原始输入表面观察重叠值为0，但assessment为input_surface_crossing_depth_unresolved，'
        '完整有效PhysX穿透仍未测量；不据此宣称没有穿透。'))
    warning = current_quantify['observed_control_times']
    observed_failures = current_quantify['progress_failures']
    if observed_failures:
        pages[6]['blocks'].append(table(['本轮实际异常观察', '仿真秒'],
            [['首次抓持质量不满足', num(warning.get('first_grasp_quality_false_t'))],
             *[[record['code'], num(record['t'])] for record in observed_failures]], [12.0, 4.4]))
    if current.get('continuous', {}).get('target_operation_region_sample_count') == 0:
        pages[6]['blocks'].append(para('本轮没有进入有效目标操作区域。即使后期出现接触停滞事件，'
            '也不把它解释成已经进入腔内座口后的插入受阻。当前单次未复现历史预插入区域能力，'
            '这一观察不能独立定位模型、图像差异或动作随机性的原因。'))
    if args.validation:
        value = load(args.validation)
        declared = value.get('report_paragraphs') if isinstance(value, dict) else None
        if declared is not None:
            if not isinstance(declared, list) or not all(isinstance(v, str) for v in declared):
                raise ValueError('validation.report_paragraphs must be a list of factual strings')
            for index, text in enumerate(declared):
                pages[9]['blocks'].insert(index+1, para(text))
        else:
            pages[9]['blocks'].insert(1, para('本轮最终验证记录已绑定于source_inputs/validation.json，'
                '包括实际执行的CPU、读取和保护检查；具体逐项状态以该文件为准。'))
    h5_rows = current.get('h5_files', [])
    if h5_rows:
        pages[9]['blocks'].insert(-1, para('本轮源H5 SHA256：'+
            '；'.join(Path(row['path']).name+' '+row['sha256'] for row in h5_rows)+
            '。本轮实际读取前后H5与任务标签哈希保持一致。'))
    counts = reader['index_counts']
    reader_rows = {row['policy_type']: row for row in reader['readers']}
    pages[9]['blocks'].insert(1, para('已使用正常索引与./labsim dataset-check入口读取实际batch。'
        f'用途选择policy_evaluation，success={counts["success"]}、failure={counts["failure"]}、all_valid={counts["all_valid"]}。'
        'ACT双视角图像各'+str(reader_rows['act']['image_shapes']['side_camera_rgb'])+
        '，DP双视角各'+str(reader_rows['dp']['image_shapes']['side_camera_rgb'])+
        '，两者动作batch均为'+str(reader_rows['act']['action_shape'])+'。'
        '数值有限、观测动作时间对齐；仅验证失败轨迹回读，没有训练或优化器运行。'))
    pages[2]['blocks'].append(para('本次正式identity核查确认：实际controller只有两项财务cap不同，其他字段逐项相同；'
        '器皿/TCP/关节实际初态一致，双相机安装与标定一致。renderer帧时间和亮度存在差异，'
        '不宣称两次像素逐字相同，也不据单集差异定位模型表现变化的原因。'))
    pages[4]['blocks'].append(para('历史第一次实际失持的物理确认时刻为'+
        num(quantify['attempts'][0]['operation_end_t'], 6)+'秒，首次控制端点观察到该状态为'+
        num(quantify['observed_control_times']['first_actual_grasp_loss_observed_t'], 6)+
        '秒。前者来自240 Hz物理事件，后者来自60 Hz端点观察，二者保留各自采样口径。'))
    pages[9]['blocks'].append(para('上表801a仅表示内容生成时checkout身份。新分析与内容工具当时位于工作区，'
        '不能把801a误写为完整新分析源码的发布版本。分析实际源码SHA、输入SHA和内容生成器SHA随源清单保留；'
        '最终发布提交与完整代码SHA由随包发布凭据绑定。正式仿真执行提交仍为801a，不受后续文档整理影响。'))

    # Keep history's applicable measurements and the current raw terminal
    # diagnostics on independent pages. This composition is intentionally
    # twelve logical pages; the authoring/render gate still verifies layout.
    historical_stats = historical['continuous']['target_error_within_episode']
    historical_minimum = historical['continuous']['minimum']
    target_rows = []
    for key, label, scale in [('target_lateral_error_m', '横向误差 mm', 1000),
            ('target_tilt_rad', '倾角 rad', 1), ('target_yaw_error_rad', '方位误差 rad', 1)]:
        record = historical_stats[key]
        target_rows.append([label, record['n'], num(record['mean'], 8, scale),
            num(record['minimum'], 8, scale), num(historical_minimum[key]['t'], 6)])
    history_target_page = page('历史目标操作区域的适用误差',
        para('历史仅在entrance_region与current_attempt_route同时成立的实际控制端点统计目标误差。'
             '适用窗口为'+num(quantify['observed_control_times']['first_target_operation_region_t'], 6)+'至'+
             num(quantify['observed_control_times']['last_target_operation_region_t'], 6)+'秒，共'+
             str(historical['continuous']['target_operation_region_sample_count'])+'个端点。'),
        image('evidence:media/historical_figures_02/03_historical_applicable_errors.png',
            '只绘制历史适用区内端点；模型未接收这些私有几何误差。', cap=9.0),
        table(['历史适用区指标', 'n', '均值', '最小值', '最小值时刻 s'], target_rows,
            [4.2, 1.2, 3.2, 3.2, 4.6]),
        para('横向误差均值约'+num(historical_stats['target_lateral_error_m']['mean'], 7, 1000)+
             ' mm、最小约'+num(historical_stats['target_lateral_error_m']['minimum'], 6, 1000)+
             ' mm，倾角均值约'+num(historical_stats['target_tilt_rad']['mean'], 8)+' rad。'
             '各分量最小值发生在不同时间，不能拼成一个同时达到的对准姿态。'
             '历史未达到有效插入门控，因此原始depth或legacy raw insert数值不用于宣称有效装载。'))
    terminal_table, terminal_text = pages[5]['blocks'][-2:]
    pages[5]['blocks'] = pages[5]['blocks'][:-2]
    terminal_frame = last_frame(media[1]['screenshots'])
    terminal_page = page('本轮实际张爪与终态承托位置',
        para('该页记录实际终态物理量，与任务合法释放门控分别说明。器皿实际已经脱离双指接触，'
             '但承重位置、目标容纳与撤离净空不满足完整装载。'),
        terminal_table, terminal_text,
        shot(terminal_frame, '本轮完整连续轨迹的真实终帧'),
        para('末尾terminal_window稳定不等于合法释放或撤离成功。post_retreat_window仍为unavailable，'
             'stable_after_retreat保持null；原H5、独立评分和视频标注不因终帧静止而改为success。'))
    if terminal_frame:
        pages[7]['blocks'] = [block for block in pages[7]['blocks']
            if block.get('type') != 'image' or block.get('path') != terminal_frame['evidence_path']]
    if args.formal_figure:
        # Keep the detailed chart readable on the visual-evidence page rather
        # than squeezing it between three current-metric tables. The replaced
        # historical warning frame remains in the full engineering evidence.
        graph = next(block for block in pages[6]['blocks']
                     if block.get('type') == 'image')
        pages[6]['blocks'] = [block for block in pages[6]['blocks'] if block is not graph]
        graph = dict(graph, height_cap_cm=9.0)
        historical_warning = pick_frame(media[0]['screenshots'], 'first_quality_warning')
        if historical_warning is None:
            raise ValueError('Expected historical warning frame to replace with the formal chart')
        replacements = 0
        for index, block in enumerate(pages[7]['blocks']):
            if block.get('type') == 'image' and block.get('path') == historical_warning['evidence_path']:
                pages[7]['blocks'][index] = graph
                replacements += 1
        if replacements != 1:
            raise ValueError('Expected exactly one warning image in the visual-evidence page')
    # Layout-only condensation of the same frozen cost facts: retain both
    # original numerical tables and combine narrative into two paragraphs.
    cost_tables = [block for block in pages[8]['blocks'] if block['type'] == 'table']
    finish_note = ('策略主动finish，未触发USD20预算截断；与P9外部预算停止分列，结果由独立scorer给出。'
        if current_gpt.get('termination_reason') == 'POLICY_FINISH_REQUEST' else
        '本轮终止为'+str(current_gpt.get('termination_reason'))+'，结果由独立scorer给出。')
    cost_scope = (finish_note+'授权额外USD20/480网络次，仅1集；累计上限USD49.267746/857次。'
        '原377次/USD29.267746账本只读、前缀保留，另外9集未授权。关闭后累计USD'+
        num(ledger['total_estimated_usd'], 6)+'/'+str(ledger['total_network_attempts'])+
        '次；成本按episode精确标签归属，原51次不含同UUID离线QA。')
    price_scope = ('费用按2026-10-26冻结配置：输入$10/M、输出$50/M、缓存$1/M；实际账单及倍率未知。'
        '原51次均值外推160次约$13.098，80k输入+1024输出的保守单次预留$0.8512；'
        '$20不保证160次含重试，每次请求前检查预留，余额不足即停。wrapper无独立起点，整进程N/A；'
        '组件合计不含全部几何审计和父进程开销，不作整进程时间或用文件时戳补算。')
    pages[8]['blocks'] = [cost_tables[0], para(cost_scope), para(price_scope), cost_tables[1]]
    pages.insert(5, history_target_page)
    pages.insert(7, terminal_page)
    output.mkdir(parents=True, exist_ok=False)
    source_dir = output/'source_inputs'
    source_dir.mkdir()
    paths = dict(identity=identity_path, environment_comparison=comparison_path,
        historical_metrics=historical_metrics, historical_quantification=historical_quantification,
        formal_quantification=formal_quantification,
        terminal_contact_observation=terminal_path,
        official_reader_summary=reader_path,
        formal_metrics=args.formal_metrics, formal_result=ep/'result.json',
        formal_gpt_summary=ep/'gpt_control/summary.json', formal_progress_summary=ep/'progress_summary.json',
        formal_process_exit=process_exit_path(run, ep), protocol=args.protocol,
        authorization=args.authorization, original_ledger=original_ledger_path,
        authorized_ledger=args.ledger, historical_media=media[0]['receipt'], formal_media=media[1]['receipt'])
    if args.validation:
        paths['validation'] = args.validation
    for name, filename in (('formal_closure_check', 'formal_debug04_01_closed.json'),
            ('formal_identity_check', 'formal_identity_01.json'),
            ('formal_schema_check', 'formal_schema_01.json'), ('formal_drift_check', 'formal_drift_01.json')):
        paths[name] = evidence/'validation'/filename
    sources = []
    for name, path in paths.items():
        path = Path(path).resolve()
        copied = source_dir/(name+'.json')
        shutil.copyfile(path, copied)
        sources.append(dict(path='content:source_inputs/'+copied.name,
            source_absolute_path=str(path), sha256=sha(path), bytes=path.stat().st_size))
    content = dict(schema='labsim.Gpt_debug04_v1.report_content.v1',
        title='LabSim 历史GPT策略恢复与单集装载评测报告',
        subtitle='历史gpt_debug_04只读量化与当前标准场景独立复测 2026年11月3日',
        header='LabSim 器皿装载 历史策略恢复与单集复测',
        author='LabSim 项目组', pages=pages, facts=facts, sources=sources,
        provenance=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            tool_sha256=sha(__file__), source_files=sources,
            content_generation_checkout_commit=subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            content_generation_worktree_dirty=bool(subprocess.check_output(
                ['git', 'status', '--porcelain'], cwd=root).strip()),
            analysis_code_identity='Actual source hashes and final publication receipt, not checkout SHA alone',
            historical_and_formal_denominators_independent=True,
            actual_formal_episode_count=1, original_sources_modified=False,
            artifact_authoring_performed=False, model_calls_by_builder=0))
    (output/'report_content.json').write_text(json.dumps(content, ensure_ascii=False,
        indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (output/'RESULTS.md').write_text(markdown(content), encoding='utf-8')
    (output/'content_receipt.json').write_text(json.dumps(dict(
        schema='labsim.Gpt_debug04_v1.report_content_receipt.v1', facts=facts,
        content_sha256=sha(output/'report_content.json'), markdown_sha256=sha(output/'RESULTS.md'),
        authoring_performed=False, page_count=len(pages)), ensure_ascii=False, indent=2)+'\n')
    return content


def main(argv=None):
    args = parser().parse_args(argv)
    content = build(args)
    print(json.dumps(dict(output=str(args.output), pages=len(content['pages']),
        formal_episode_id=content['facts']['formal_episode_id'], model_calls=0,
        docx_authored=False), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
