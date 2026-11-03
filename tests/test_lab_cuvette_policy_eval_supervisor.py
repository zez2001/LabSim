"""Exercise real git identity gates without starting Isaac or a provider."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.run_lab_cuvette_policy_eval import main, gpt_command


@pytest.fixture
def source(tmp_path):
    repo = tmp_path/'source'
    repo.mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'config.json').write_text('{"layout":"standard"}')
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.email=fixture@example.invalid',
                    '-c','user.name=fixture','commit','-qm','fixture'],check=True)
    sha=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    protocol=tmp_path/'protocol.json'
    protocol.write_text(json.dumps({'environment':{'runtime_commit':sha},
        'locked_source_files':{'config.json':hashlib.sha256((repo/'config.json').read_bytes()).hexdigest()},
        'status':'preflight_candidate_not_yet_formal_frozen'}))
    args=['--protocol',str(protocol),'--checkout',str(repo),'--output',str(tmp_path/'out'),
          '--group','gpt6','--phase','diagnostic','--trial-id','check','--check-only']
    return repo,protocol,args


def test_clean_frozen_source_check_is_read_only(source,capsys):
    repo,protocol,args=source
    assert main(args)==0
    result=json.loads(capsys.readouterr().out)
    assert result['valid'] and not result['actual_models_started'] and not result['output_created']
    assert not (repo.parent/'out').exists()


def test_formal_requires_completed_preflight(source):
    repo,protocol,args=source
    args[args.index('diagnostic')]='formal'
    with pytest.raises(ValueError,match='preflight-passed'):
        main(args)
    assert not (repo.parent/'out').exists()


def test_changed_source_cannot_start_models(source):
    repo,protocol,args=source
    (repo/'config.json').write_text('{"layout":"changed"}')
    with pytest.raises(ValueError,match='clean runtime'):
        main(args)
    assert not (repo.parent/'out').exists()


def test_wrong_fingerprint_cannot_start_models(source):
    repo,protocol,args=source
    cfg=json.loads(protocol.read_text())
    cfg['locked_source_files']['config.json']='0'*64
    protocol.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='Frozen source differs'):
        main(args)


@pytest.mark.parametrize('diagnostic,max_calls',[(True,1),(False,160)])
def test_generated_gpt_route_uses_one_episode_and_real_cli(diagnostic,max_calls):
    from scripts.labsim_cli import parser
    command=gpt_command(['python','scripts/labsim_cli.py'],
        ['--project-version','Project_release_v1','--headless','--record-mode','eval',
         '--record-purpose','policy_evaluation','--progress'],Path('/source'),
        {'gpt6':{'provider_config':'provider.json','max_calls':160},
         'budget':{'ledger':'/ledger.json'}},Path('/result'),diagnostic)
    parsed=parser().parse_args(command[2:])
    assert parsed.episodes==1 and parsed.max_calls==max_calls
    assert parsed.project_version=='Project_release_v1' and parsed.progress
