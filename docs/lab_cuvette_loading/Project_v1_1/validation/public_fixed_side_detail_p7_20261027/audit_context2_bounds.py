"""Offline P7/context2 size audit of closed GPT05 public projections.

No HTTP client is instantiated. Private provider items are hash placeholders;
the old real reservation supplies only a conservative aggregate byte residual.
"""
import argparse
import base64
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


def latest_turn(items):
    receipts = [i for i, item in enumerate(items) if item.get('type') == 'function_call_output']
    if not receipts:
        return [], []
    start = receipts[-2]+1 if len(receipts)>1 else 1
    end = receipts[-1]+1
    return copy.deepcopy(items[start:end]), list(range(start, end))


def placeholder_size(item):
    # Include its following comma+space; cancelling these terms preserves the
    # bound even when the original private representation contained no text.
    return len(json.dumps(item, ensure_ascii=False).encode())+2


def private_range(original_bound, original_projected_bound, original_items, selected, projected_bound):
    redacted = [i for i,item in enumerate(original_items)
        if item.get('type') == 'private_provider_item_not_persisted']
    kept = [i for i in redacted if i in selected]
    removed = [i for i in redacted if i not in selected]
    residual = original_bound-original_projected_bound
    if not redacted:
        assert residual == 0, 'Known old payload differs from its actual reservation'
    all_bytes = residual+sum(placeholder_size(original_items[i]) for i in redacted)
    assert all_bytes >= 0
    lower = projected_bound-sum(placeholder_size(original_items[i]) for i in kept)
    return dict(all_private_bytes=all_bytes, kept=kept, removed=removed,
        lower=lower, upper=lower+(all_bytes if kept else 0))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    repo, source, output = args.repo.resolve(), args.source.resolve(), args.output.resolve()
    if output.exists():
        raise FileExistsError('Refusing to replace bound audit')
    if output.is_relative_to(source.parent.parent) or source.parent.parent.is_relative_to(output):
        raise ValueError('Audit output must be separate from the entire closed run')
    sys.path.insert(0, str(repo))
    from policy.backends.cubence import input_token_bound, load_config
    from policy.backends.cubence_project_v1_1_side_detail import (
        DEFAULT_PROFILE, SYSTEM_PROMPT, PublicFixedSideDetailClient, _Capture,
        _closed_source_proof)
    cfg = load_config(DEFAULT_PROFILE)
    assert cfg['max_context_messages'] == 2
    proof_path = source.parent.parent/'process_exit.json'
    proof = _closed_source_proof(source, proof_path)
    controller_path, ledger_path = source/'controller.json', args.ledger.resolve()
    controller = json.loads(controller_path.read_text())
    original_cfg = controller['provider_config']
    assert original_cfg['max_context_messages'] == 4
    assert cfg['action_limits'] == original_cfg['action_limits']
    assert cfg['images'] == original_cfg['images']
    ledger_bytes = ledger_path.read_bytes()
    attempts = json.loads(ledger_bytes)['attempts']
    tracked = {p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (proof_path, controller_path, ledger_path)}

    def remember(path):
        tracked[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_bytes()

    def restore(value, origin):
        if isinstance(value, list):
            return [restore(item, origin) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'image_url' and isinstance(item, dict):
                    path = (origin/item['path']).resolve()
                    assert path.is_relative_to(source)
                    data = remember(path)
                    assert hashlib.sha256(data).hexdigest() == item['sha256']
                    result[key] = 'data:image/jpeg;base64,'+base64.b64encode(data).decode()
                else:
                    result[key] = restore(item, origin)
            return result
        return value

    def body(items, prompt):
        return dict(model=cfg['model'], input=items,
            instructions=prompt+'\nAction limits: '+json.dumps(cfg['action_limits']),
            tools=controller['tool_schema'], max_output_tokens=cfg['max_output_tokens'],
            store=False, reasoning={'effort': cfg['reasoning_effort']}, parallel_tool_calls=False)

    rows, source_reservations = [], []
    folders = sorted((source/'temporal_visual_context').glob('decision_*'))
    with tempfile.TemporaryDirectory(prefix='labsim-p7-bound-') as name:
        scratch = Path(name)
        capture = _Capture(cfg)
        client = PublicFixedSideDetailClient(capture, scratch)
        for index, folder in enumerate(folders):
            record_path = folder/'input_items_manifest.json'
            record = json.loads(remember(record_path))
            assert index == record['decision_index']
            original_items = restore(record['input_items_public_projection'], folder)
            current = source/'observations'/f'decision_{index:06d}'
            target = scratch/'observations'/f'decision_{index:06d}'
            target.mkdir(parents=True)
            for filename in ('public_observation.json', 'side_camera.jpg', 'wrist_camera.jpg', 'manifest.json'):
                remember(current/filename)
                shutil.copy2(current/filename, target/filename)
            turn, selected = latest_turn(original_items)
            items = [original_items[0], *turn, original_items[-1]]
            assert len(items[-1]['content']) == 5
            client.responses(items, instructions=SYSTEM_PROMPT, tools=controller['tool_schema'],
                label=record['request_label'])
            delegated = capture.last_input
            projected_bound = input_token_bound(body(delegated, SYSTEM_PROMPT), 10**9)
            original_projected_bound = input_token_bound(body(original_items, controller['prompt']), 10**9)
            entries = [item for item in attempts if item['label'] == record['request_label']]
            assert entries and len({row['reservation_input_tokens'] for row in entries}) == 1
            original_bound = entries[0]['reservation_input_tokens']
            # The old real reservation and byte-equivalent known fields determine
            # total serialized private-item bytes, but cannot apportion those
            # bytes between the last two turns. Allocate them all to retained
            # private items, an intentionally pessimistic bound.
            interval = private_range(original_bound, original_projected_bound,
                original_items, selected, projected_bound)
            kept, removed = interval['kept'], interval['removed']
            lower, upper = interval['lower'], interval['upper']
            row = dict(decision_index=index, request_label=record['request_label'],
                image_count=json.loads((scratch/'temporal_visual_context'/folder.name/'input_items_manifest.json').read_text())['total_image_count'],
                old_context4_real_reservation=original_bound,
                old_public_placeholder_bound=original_projected_bound,
                private_serialized_total_inferred_bytes=interval['all_private_bytes'],
                private_items_retained=len(kept), private_items_removed=len(removed),
                P7_context2_public_placeholder_bound=projected_bound,
                P7_context2_private_range_lower=lower,
                P7_context2_private_conservative_upper=upper,
                margin_to_80000_at_conservative_upper=80000-upper,
                exact_reconstructable_input=not kept,
                API_sent=False, tools_executed=False)
            rows.append(row)
            source_reservations.extend({key: entry.get(key) for key in (
                'request_id', 'label', 'status', 'reservation_input_tokens',
                'reservation_output_tokens', 'reserved_usd', 'charged_estimate_usd')} for entry in entries)
    assert rows and all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path,digest in tracked.items())
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(schema='Project_v1_1.P7_context2.closed_public_bound_audit.v1',
        API_sent=False, actions_executed=0, source_runtime=proof['runtime_commit'],
        current_profile='context2 + fixed side detail; P6 context4 unchanged',
        decisions=len(rows), private_content_read_or_reconstructed=False,
        private_size_method='Old real reservation minus byte-equivalent original known/projected payload; no private content inferred. For retained private items allocate all aggregate private bytes to the retained turn.',
        limitations=['Only these closed public frames/tool responses were replayed, not a new policy rollout.',
            'Private placeholders are not the actual provider items or a sendable full request.',
            '80k is the existing local heuristic, not tokenizer/account billing or future request guarantee.',
            'Actual live requests remain checked before network/reservation; future larger responses can still be refused.'],
        max_public_placeholder_bound=max(row['P7_context2_public_placeholder_bound'] for row in rows),
        max_private_conservative_upper=max(row['P7_context2_private_conservative_upper'] for row in rows),
        min_margin_to_80000=min(row['margin_to_80000_at_conservative_upper'] for row in rows),
        all_closed_conservative_uppers_within_limit=all(row['P7_context2_private_conservative_upper'] <= 80000 for row in rows),
        rows=rows, source_SHA256={str(path): digest for path,digest in tracked.items()},
        all_original_sources_unchanged=True)
    summary['implementation_SHA256'] = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).resolve(), repo/'policy/backends/cubence_project_v1_1_side_detail.py', DEFAULT_PROFILE)}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (output/'source_reservation_evidence.json').write_text(json.dumps(source_reservations,indent=2)+'\n')
    with (output/'bounds.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({key: summary[key] for key in ('API_sent','decisions',
        'max_public_placeholder_bound','max_private_conservative_upper','min_margin_to_80000')}))
    return summary


if __name__ == '__main__':
    main()
