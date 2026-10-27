"""Run intent and startup identity; no physical state or qualification changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RECORD_PURPOSES = ('demonstration', 'policy_evaluation', 'lifecycle_diagnostic', 'resource_probe')


def record_purpose(value, *, allow_unknown=False):
    value = str(value or 'unknown')
    if value not in RECORD_PURPOSES and not (allow_unknown and value == 'unknown'):
        raise ValueError('record_purpose must explicitly name one of ' + ', '.join(RECORD_PURPOSES))
    return value


def select_record_purpose(explicit, *, backend, execution_purpose, sequence=False):
    """Select by the declared invocation, never by outcome, duration or frames."""
    if sequence:
        selected = explicit or 'lifecycle_diagnostic'
        if selected not in ('lifecycle_diagnostic', 'resource_probe'):
            raise ValueError('Acceptance --sequence records must declare lifecycle_diagnostic or resource_probe')
    else:
        selected = explicit or ('demonstration' if backend == 'teacher' and execution_purpose in ('demo', 'collect')
                                else 'policy_evaluation')
    return record_purpose(selected)


def startup_summary(cfg, *, source_config, output, backend, geometry_audit=None):
    from omegaconf import OmegaConf
    from demos.lab_cuvette_project_release_v1.contract import scene_contract
    resolved = OmegaConf.to_container(cfg, resolve=True)
    return dict(schema='labsim.Project_release_v1.startup.v1',
        version=str(cfg.version), task=str(cfg.task_type), scene=str(cfg.scene_mode),
        backend=str(backend), asset_id=str(cfg.asset_id),
        record_purpose=record_purpose(cfg.release.get('record_purpose'), allow_unknown=True),
        record_mode=str(cfg.release.record_mode), output=str(Path(output).resolve()),
        config=str(Path(source_config).resolve()),
        source_config_sha256=hashlib.sha256(Path(source_config).read_bytes()).hexdigest(),
        resolved_config_sha256=hashlib.sha256(OmegaConf.to_yaml(resolved).encode()).hexdigest(),
        project_scene_fingerprint=scene_contract(cfg, geometry_audit)['frozen_scene_sha256'])


def announce_startup(cfg, *, source_config, output, backend, geometry_audit=None):
    summary = startup_summary(cfg, source_config=source_config, output=output,
                              backend=backend, geometry_audit=geometry_audit)
    (Path(output) / 'startup_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('LABSIM_STARTUP', json.dumps(summary, ensure_ascii=False), flush=True)
    return summary
