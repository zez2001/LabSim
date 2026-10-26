"""Translate the upstream main.py arguments into the same Project_v1 launcher."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build_project_argv(args):
    if args.backend != 'numpy':
        raise ValueError('Project_v1 preserves the CPU PhysX baseline; use --backend numpy')
    if args.no_video:
        raise ValueError('Project_v1 records both cameras; --no-video is not a supported release mode')
    if args.subtask not in (None, 'loading') or args.initial_state or args.replay_episode:
        raise ValueError('Project_v1 native entry supports complete standard loading; historical diagnostics/replay retain their original entries')
    if args.layout_mode != 'standard':
        raise ValueError('Project_v1 native entry supports the fixed standard scene only')
    if args.env_mode not in ('teacher', 'serve', 'audit'):
        raise ValueError('Project_v1 supports --env-mode teacher, serve or audit')
    if not args.output:
        raise ValueError('Project_v1 requires an explicit new --output directory')
    backend = 'rpc' if args.env_mode == 'serve' else args.policy_backend
    config = Path(args.project_config)
    output = Path(args.output)
    argv = ['--config', str(config if config.is_absolute() else ROOT / config),
        '--backend', backend, '--layout-mode', 'standard', '--seed', str(args.seed),
        '--episodes', str(args.episodes), '--port', str(args.port),
        '--max-calls', str(args.max_calls), '--output', str(output if output.is_absolute() else ROOT / output)]
    if args.headless:
        argv.append('--headless')
    if args.env_mode == 'audit':
        argv.append('--audit-only')
    for name in ('provider_config', 'budget_ledger', 'asset_id'):
        value = getattr(args, name, None)
        if value:
            argv += ['--' + name.replace('_', '-'), str(value)]
    return argv
