"""CPU-only Progress analysis and report commands for lab_cuvette_loading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in (('episode', 'Analyze a closed episode directory or root HDF5'),
                            ('index', 'Analyze closed members of a relative-link or copied HDF5 index')):
        command = sub.add_parser(name, help=help_text)
        command.add_argument('source', type=Path)
        command.add_argument('--output', type=Path, required=True, help='New output directory, outside source episodes')
        command.add_argument('--config', type=Path, help='Actual task YAML; defaults to episode config.yaml or HDF5 configuration_json')
        command.add_argument('--no-report', action='store_true', help='Skip the HTML/SVG report')
    report = sub.add_parser('report', help='Build a self-contained HTML/SVG report with real video references')
    report.add_argument('progress_directory', type=Path)
    report.add_argument('--episode', type=Path, help='Original episode containing the real side/wrist MP4 and frame timestamps')
    report.add_argument('--copy-videos', action='store_true', help='Copy genuine original side/wrist MP4 into report/media for handoff')
    compare = sub.add_parser('compare', help='Compare exact online/offline causal snapshots, events and final stages')
    compare.add_argument('online_directory', type=Path)
    compare.add_argument('offline_directory', type=Path)
    compare.add_argument('--output', type=Path, help='New consistency JSON file; never overwrite an earlier comparison')
    args = parser.parse_args(argv)
    try:
        if args.command == 'compare':
            from .offline import compare_progress
            result = compare_progress(args.online_directory, args.offline_directory, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['equal'] else 1
        elif args.command == 'report':
            from .report import generate_report
            print(generate_report(args.progress_directory, args.episode, copy_videos=args.copy_videos))
        else:
            from .offline import analyze_episode, analyze_index
            function = analyze_episode if args.command == 'episode' else analyze_index
            result = function(args.source, args.output, config_path=args.config,
                              make_report=not args.no_report)
            concise = {key: result.get(key) for key in ('progress_complete', 'termination_domain',
                'unfinished_requirement', 'output_integrity', 'recording', 'episodes', 'excluded') if key in result}
            print(json.dumps(concise, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print('Progress error: ' + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
