"""Discover installed runtime paths without modifying Isaac or model environments."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def asset_root_from_config(cfg):
    """Return the root containing assets/... without requiring a host-specific path."""
    value = Path(str(cfg.get('asset_directory', 'assets/lab_cuvette_loading/V0_demo04')))
    if value.is_absolute():
        parts = value.parts
        if 'assets' in parts:
            return Path(*parts[:parts.index('assets')])
    return ROOT


def logical_path(path, cfg):
    value = Path(path).resolve()
    for root in (asset_root_from_config(cfg), ROOT):
        try:
            return value.relative_to(root).as_posix()
        except ValueError:
            pass
    raise ValueError('Undeclared path outside selected project/asset roots: ' + str(value))


def portable_config(value, cfg):
    """Canonicalize declared paths, preserving all physical numeric settings."""
    if isinstance(value, dict):
        return {key: portable_config(item, cfg) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_config(item, cfg) for item in value]
    if isinstance(value, str) and Path(value).is_absolute():
        if value == '/World' or value.startswith('/World/') or value == '/Asset' or value.startswith('/Asset/'):
            return value  # USD prim identity, not a host filesystem path
        return logical_path(value, cfg)
    return value


def isaac_paths():
    distribution = importlib.metadata.distribution('isaacsim')
    package = Path(distribution.locate_file('isaacsim')).resolve()
    extensions = package / 'extscache'
    usd = sorted(extensions.glob('omni.usd.libs-*'))
    physx = sorted(extensions.glob('omni.usd.schema.physx-*'))
    if not usd or not physx:
        raise RuntimeError('Isaac USD/PhysX extensions unavailable in selected LABSIM_PYTHON')
    return dict(package=package, usd=usd[-1], physx=physx[-1],
                environment=Path(sys.prefix).resolve())


def geometry_site(required=True):
    explicit = os.environ.get('LABSIM_GEOMETRY_SITE')
    candidates = ([Path(explicit).expanduser()] if explicit else [])
    candidates += [Path.home() / '.local/share/labsim/geometry/lib/python3.11/site-packages']
    for directory in candidates:
        if (directory / 'shapely').is_dir():
            return str(directory.resolve())
    try:
        version = importlib.metadata.version('shapely')
        if tuple(int(p) for p in version.split('.')[:2]) >= (2, 1):
            return ''
    except importlib.metadata.PackageNotFoundError:
        pass
    if required:
        raise RuntimeError('Shapely>=2.1 is required for the existing geometry audit. Set '
                           'LABSIM_GEOMETRY_SITE to its isolated Python3.11 site-packages; '
                           'do not install it into Isaac or a model environment.')
    return None


def selected_asset_root():
    """Prefer an explicit root or the complete pinned download cache."""
    explicit = os.environ.get('LABSIM_ASSET_ROOT')
    if explicit:
        return Path(explicit).expanduser().resolve()
    from demos.lab_cuvette_project_v1.assets import load_lock, cache_root, check_assets
    lock = load_lock()
    cached = cache_root() / lock['revision']
    if cached.is_dir() and check_assets(cached)['all_files_verified']:
        return cached
    return ROOT


def usd_environment():
    paths = isaac_paths()
    env = dict(os.environ)
    for name, values in (
        ('PYTHONPATH', [ROOT, paths['physx'], paths['usd']]),
        ('LD_LIBRARY_PATH', [paths['physx'] / 'bin', paths['usd'] / 'bin',
                             paths['environment'] / 'lib', paths['package'] / 'kit']),
        ('PXR_PLUGINPATH_NAME', [paths['physx'] / 'plugins/PhysxSchema/resources']),
    ):
        existing = env.get(name)
        env[name] = os.pathsep.join([*(str(v) for v in values), *([existing] if existing else [])])
    env['LABSIM_PYTHON'] = sys.executable
    return env


def run_usd(arguments, *, check=True):
    return subprocess.run([sys.executable, *map(str, arguments)], cwd=ROOT,
                          env=usd_environment(), check=check)


def resolve_config(config):
    """New release-only overrides; historical files and their hashes stay intact."""
    from omegaconf import OmegaConf
    cfg = OmegaConf.create(OmegaConf.to_container(config, resolve=True))
    cfg.env.shapely_site = geometry_site()
    asset_root = selected_asset_root()
    if asset_root != ROOT:
        directory = asset_root
        for key in ('asset_directory', 'derived_directory', 'asset_registry'):
            value = OmegaConf.select(cfg, key)
            if value and not Path(value).is_absolute():
                OmegaConf.update(cfg, key, str(directory / value))
        for key in ('source.instrument', 'source.vessel', 'source.vessel_collision', 'robot.usd_path'):
            value = OmegaConf.select(cfg, key)
            if value and not Path(value).is_absolute():
                OmegaConf.update(cfg, key, str(directory / value))
    registry_path = ROOT / str(cfg.asset_registry)
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        record = registry['assets'][str(cfg.asset_id)]
        selected = ROOT / str(cfg.source.vessel)
        import hashlib
        actual = hashlib.sha256(selected.read_bytes()).hexdigest()
        if actual != record['asset_sha256']:
            raise RuntimeError('Selected release asset differs from its registered SHA256: ' + str(selected))
        cfg.asset_selection.asset_sha256 = actual
        cfg.asset_selection.registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        cfg.asset_selection.source_sha256 = record['source']['sha256']
        cfg.asset_selection.validation_scope = 'Release registry bytes and selected asset SHA; unchanged geometric metadata, independent geometry and physical checks remain required'
    return cfg


if __name__ == '__main__':
    if sys.argv[1:2] == ['usd']:
        raise SystemExit(run_usd(sys.argv[2:], check=False).returncode)
    print(json.dumps({k: str(v) for k, v in isaac_paths().items()}, indent=2))
