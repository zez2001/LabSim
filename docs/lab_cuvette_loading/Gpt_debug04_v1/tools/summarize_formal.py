"""Reuse the source-backed Progress export for one new closed formal episode."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


def summarize(progress, episode_metrics, output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    path = Path(__file__).with_name('summarize_historical.py')
    spec = importlib.util.spec_from_file_location('debug04_reused_progress_export', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    episodes = json.loads(Path(episode_metrics).read_text())
    started = [row for row in episodes if row.get('purpose') == 'formal' and row.get('started')]
    if len(started) != 1 or started[0].get('analysis_evidence_valid') is not True:
        raise ValueError('One analysis-valid closed formal episode is required')
    with tempfile.TemporaryDirectory(prefix='labsim-debug04-source-backed-export-') as temporary:
        selected = Path(temporary)/'selected_episode.json'
        selected.write_text(json.dumps(started, ensure_ascii=False))
        staging = Path(temporary)/'export'
        value = module.summarize(Path(progress), selected, staging)
        # Only wrapper identity/scope changes. All source values and labels are
        # exactly the existing export, then bound to the persistent source.
        value['schema'] = 'labsim.Gpt_debug04_v1.formal_quantification.v1'
        value['analysis_scope'] = 'one explicitly authorized new formal episode; nine planned episodes unstarted and not authorized; historical/P9/pi05 episodes excluded'
        value['sources'].pop(str(selected.resolve()))
        value['sources'][str(Path(episode_metrics).resolve())] = module.file_sha256(episode_metrics)
        value['reused_export_tool'] = dict(path=str(path.resolve()), sha256=module.file_sha256(path),
            value_changes='wrapper schema/scope and temporary-to-persistent metrics source binding only; source metrics and task labels unchanged')
        output.mkdir(parents=True, exist_ok=False)
        (output/'quantification.json').write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        shutil.copy2(staging/'stages.csv', output/'stages.csv')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('progress',type=Path)
    parser.add_argument('--episode-metrics',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(argv)
    value = summarize(args.progress,args.episode_metrics,args.output)
    print(json.dumps(dict(episode_id=value['episode_id'],control_steps=value['control_steps'],
        events=value['complete_event_count'],attempts=value['progress_attempt_count'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
