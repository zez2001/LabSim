"""V0_demo02 static acceptance entry and explicitly gated workflow request."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PHASES = ['RESET', 'APPROACH_SOURCE', 'GRASP', 'EXTRACT', 'TRANSPORT', 'ALIGN',
          'INSERT', 'SUPPORT_TRANSFER', 'OPEN', 'RETREAT', 'VERIFY']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--review', action='store_true', help='render static assets only; no task trajectory')
    parser.add_argument('--scene', type=Path, default=ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified/scene_review.usda')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if not args.review:
        acceptance = json.loads((ROOT/'docs/lab_cuvette_loading/V0_demo02/acceptance.json').read_text())
        result = dict(version='V0_demo02', status='BLOCKED_STATIC_ACCEPTANCE',
                      physical_episode_executed=False, simulation_seconds=None,
                      workflow_success=False, native_pair_success=False,
                      scene_correspondence_accepted=False, real_calibrated=False,
                      data_eligible=False, phases_requested=PHASES, phases_executed=[],
                      post_retreat_window=dict(available=False, status='unavailable', reason='no new physical workflow'),
                      stable_after_retreat=None, terminal_window=None,
                      blockers=acceptance['blockers'],
                      note='No exterior holder or synthetic single-slot rack fallback. Full executor adaptation and physical batches remain unexecuted until native scene acceptance.')
        (args.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(result['status'], *result['blockers'], sep='\n', flush=True)
        return
    from isaacsim import SimulationApp
    app = SimulationApp(dict(headless=args.headless, width=1920, height=1080,
                             extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    try:
        from demos.lab_cuvette_demo02.review import render
        render(args, app)
    except BaseException:
        import traceback
        traceback.print_exc()
        (args.output/'error.txt').write_text(traceback.format_exc())
        raise
    finally:
        app.close()


if __name__ == '__main__':
    main()
