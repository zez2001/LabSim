"""Read-only final protection and tested/runtime file-identity receipt."""
import argparse, datetime, hashlib, json, subprocess, sys
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def git(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,text=True).strip()


def verify(root,baseline,output,runtime_commit,asset_root=None,closed_run_proof=None):
    root=Path(root).resolve(); output=Path(output)
    if output.exists():raise FileExistsError(output)
    old=json.loads(Path(baseline).read_text()); final=git(root,'rev-parse','HEAD')
    files=[]
    for name,record in old['files'].items():
        p=root/name
        files.append(dict(path=name,expected_sha256=record['sha256'],actual_sha256=sha(p) if p.is_file() else None,
                          unchanged=p.is_file() and p.stat().st_size==record['bytes'] and sha(p)==record['sha256']))
    # These trees include physical assets/configuration, controllers, independent
    # scoring/reward, collectors, readers and colleagues' additional scenes.
    protected=['assets','config/lab_cuvette_loading/Project_release_v1','demos/lab_cuvette_env_v1',
               'demos/lab_cuvette_size_v1','demos/lab_cuvette_project_v1_1','demos/lab_cuvette_project_release_v1',
               'tasks/lab_cuvette_loading_project_release.py','tasks/lab_cuvette_loading_env_v1.py',
               'tasks/lab_cuvette_loading_env_v1_scorer.py','collectors','SLAI_Lab','local_assets']
    changes=git(root,'diff','--name-only',old['baseline_commit'],final,'--',*protected).splitlines()
    all_changes=git(root,'diff','--name-only',old['baseline_commit'],final).splitlines()
    allowed_prefixes=('demos/lab_cuvette_progress_v1/',
        'config/lab_cuvette_loading/Progress_v1_2/',
        'docs/lab_cuvette_loading/Progress_v1_2/',
        'docs/agent_handoff/Progress_v1_2_current/',
        'tests/test_lab_cuvette_progress_', 'tests/test_lab_cuvette_progress12_')
    allowed_files={'README.md','README_CN.md','README_EN.md',
        '.github/workflows/cpu-contracts.yml','scripts/labsim_cli.py',
        'docs/agent_handoff/package.json'}
    outside_scope=[name for name in all_changes if name not in allowed_files
        and not name.startswith(allowed_prefixes)]
    keys=['demos/lab_cuvette_progress_v1','config/lab_cuvette_loading/Progress_v1_2',
          'scripts/labsim_cli.py','tasks/lab_cuvette_loading_project_release.py']
    tested=git(root,'diff','--name-only',runtime_commit,final,'--',*keys).splitlines()
    identities=[]
    for name in git(root,'ls-tree','-r','--name-only',final,'--',*keys).splitlines():
        now=git(root,'rev-parse',final+':'+name)
        try:before=git(root,'rev-parse',runtime_commit+':'+name)
        except subprocess.CalledProcessError:before=None
        identities.append(dict(path=name,tested_git_blob=before,final_git_blob=now,identical=now==before))
    value=dict(schema='labsim.Progress_v1_2.final_protection.v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
       baseline_commit=old['baseline_commit'],runtime_commit=runtime_commit,final_commit=final,
       historical_files=files,all_historical_hashes_unchanged=all(f['unchanged'] for f in files),
       protected_runtime_tree_changes=changes,protected_runtime_unchanged=not changes,
       changed_files_since_baseline=all_changes,outside_progress_scope_changes=outside_scope,
       tested_final_key_file_comparison=identities,tested_final_key_changes=tested,
       git_worktree_status=git(root,'status','--short'),head=final,
       budget_calls_scope='Budget ledger included in historical file hashes; no model calls or HF publication performed by this revision')
    if asset_root:
        sys.path.insert(0,str(root))
        from demos.lab_cuvette_project_v1.assets import check_assets
        value['published_assets'] = check_assets(asset_root)
        assert value['published_assets']['all_files_verified']
    if closed_run_proof:
        proof=json.loads(Path(closed_run_proof).read_text())
        observed=[proof['h5'],*proof['videos'].values()]
        episode=Path(proof['run'])/'episode_0000'
        observed += [dict(path=str(episode/name),sha256=item['sha256'])
            for name,item in proof['logs'].items()]
        observed += [dict(path=str(episode/name),sha256=item['sha256'])
            for name,item in proof['progress']['integrity']['files'].items()]
        value['new_closed_run_files']=[dict(path=item['path'],expected_sha256=item['sha256'],
            actual_sha256=sha(Path(item['path'])),unchanged=sha(Path(item['path']))==item['sha256'])
            for item in observed]
        assert all(item['unchanged'] for item in value['new_closed_run_files'])
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    assert value['all_historical_hashes_unchanged'] and not changes and not outside_scope
    return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--baseline',required=True);p.add_argument('--output',required=True);p.add_argument('--runtime-commit',required=True);p.add_argument('--asset-root');p.add_argument('--closed-run-proof');a=p.parse_args()
    r=verify(a.root,a.baseline,a.output,a.runtime_commit,a.asset_root,a.closed_run_proof);print(json.dumps({k:r[k]for k in ['final_commit','all_historical_hashes_unchanged','protected_runtime_unchanged','tested_final_key_changes']},indent=2))
