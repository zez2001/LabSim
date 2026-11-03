"""Reconstruct attempt lifecycle receipts from the append-only event stream."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from .attempts import candidate_stage, confirm_stage

STAGES = ('approach_grasp', 'grasp', 'extract', 'transport', 'align', 'insert',
          'support_transfer', 'release_retreat', 'stable_complete')


def replay_attempts(events):
    """Replay lifecycle snapshots, never consulting a final summary or scorer.

    Progress v1.2 emits a full attempt receipt at start, operation end and each
    final-outcome update.  This permits reconstruction of operation timing,
    retries and eventual post-release outcomes without mutating old events.
    Missing receipts are reported rather than silently filled from a summary.
    """
    attempts = {}
    order = []
    warnings = []
    last_id = 0
    last_t = None
    lifecycle = []
    for index, event in enumerate(events):
        event_id, t = event.get('event_id'), event.get('t')
        if not isinstance(event_id, int) or event_id <= last_id:
            raise ValueError('Event IDs must strictly increase: event '+str(index))
        if not isinstance(t, (float, int)) or not math.isfinite(t) or (last_t is not None and t < last_t-1e-9):
            raise ValueError('Event times must be finite and nondecreasing: event '+str(index))
        last_id, last_t = event_id, t
        name = event.get('name')
        aid = event.get('attempt_id')
        # Confirmation toggles can legitimately continue after operation end
        # and even after the first completed stability window.  Replay these
        # increments too, so the lifecycle receipt is not silently stale.
        for stage in STAGES:
            if aid in attempts and name == stage+'_candidate':
                candidate_stage(attempts[aid], stage, t)
                break
            if aid in attempts and name == stage+'_confirmed':
                confirm_stage(attempts[aid], stage, t, event.get('candidate_start_t'))
                break
        if name not in {'attempt_started', 'attempt_ended', 'attempt_operation_ended', 'attempt_outcome_updated'}:
            continue
        receipt = (event.get('evidence') or {}).get('attempt')
        lifecycle.append(dict(event_id=event_id, name=name, t=t, attempt_id=aid))
        if not isinstance(receipt, dict):
            warnings.append(dict(event_id=event_id, reason='attempt_receipt_missing', attempt_id=aid))
            continue
        if aid is None or receipt.get('attempt_id') != aid:
            raise ValueError('Lifecycle event attempt identity does not match its receipt')
        if name == 'attempt_started':
            if aid in attempts:
                raise ValueError('Duplicate attempt_started for '+str(aid))
            if order:
                attempts[order[-1]]['next_attempt_id'] = aid
            order.append(aid)
        elif aid not in attempts:
            warnings.append(dict(event_id=event_id, reason='attempt_start_not_in_stream', attempt_id=aid))
            order.append(aid)
        attempts[aid] = copy.deepcopy(receipt)
    result = [attempts[aid] for aid in order]
    return dict(schema='labsim.Progress_v1.2.attempt_event_replay.v1',
        attempts=result, attempt_count=len(result), retry_count=max(0, len(result)-1),
        lifecycle_events=lifecycle, complete=not warnings, warnings=warnings,
        source='append-only Progress lifecycle events only; no summary or task-success input')


def verify_replay(events, summary):
    result = replay_attempts(events)
    expected = summary.get('attempts', [])
    result['attempts_match_summary'] = result['attempts'] == expected
    result['retry_count_matches_summary'] = result['retry_count'] == summary.get('retry_count')
    result['passed'] = result['complete'] and result['attempts_match_summary'] and result['retry_count_matches_summary']
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path)
    parser.add_argument('--summary', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    events = [json.loads(line) for line in args.events.read_text().splitlines() if line.strip()]
    result = verify_replay(events, json.loads(args.summary.read_text())) if args.summary else replay_attempts(events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(args.output)
    return 0 if result.get('passed', result['complete']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
