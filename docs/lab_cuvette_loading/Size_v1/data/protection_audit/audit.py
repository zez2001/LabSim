"""Read-only preservation and affine-family audit; offline USD, no SimulationApp."""
from pathlib import Path
import csv, hashlib, json, subprocess
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade
from demos.lab_cuvette_demo04.build_vessel import read_geometry, integrate_material, usd_mass_snapshot

ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).resolve().parent
BASE='c61c5bd'
ENV=ROOT/'outputs/lab_cuvette_loading/Env_v1/preinsert_continuous_latch_01'
RUNS=[ROOT/'outputs/lab_cuvette_loading/Size_v1'/n for n in ('loading_01','loading_1050_01')]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plain(v):
 if isinstance(v,np.ndarray):return v.tolist()
 if isinstance(v,(np.floating,np.integer,np.bool_)):return v.item()
 return str(v)
def write(name,value):
 p=OUT/name
 with p.open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,default=plain,allow_nan=False)+'\n')
def attrs(p):return {a.GetName():str(a.Get()) for a in p.GetAttributes()}
def baseline_hash(p):
 relative=p.relative_to(ROOT).as_posix();body=subprocess.check_output(['git','show',BASE+':'+relative],cwd=ROOT)
 if body.startswith(b'version https://git-lfs.github.com/spec/v1'):
  return next(line.decode().split('sha256:')[1] for line in body.splitlines() if line.startswith(b'oid sha256:')),'git_lfs_content_oid'
 return hashlib.sha256(body).hexdigest(),'git_blob_bytes'

import yaml
cfg0=yaml.safe_load((ENV/'episode_0000/config.yaml').read_text())
binding0=json.loads((ENV/'geometry_audit.json').read_text())['binding']['files']
instrument=ROOT/cfg0['asset_directory']/'instrument_native.usda'
stage=Usd.Stage.Open(str(instrument),Usd.Stage.LoadAll)
layers=[]
for layer in stage.GetUsedLayers():
 if not layer.realPath:continue
 p=Path(layer.realPath).resolve();old,basis=baseline_hash(p);key=p.relative_to(ROOT).as_posix()
 layers.append(dict(path=key,current_sha256=sha(p),baseline_sha256=old,baseline_hash_basis=basis,
  equals_Env_v1_git_content=sha(p)==old,equals_Env_v1_actual_run_binding=sha(p)==binding0.get(key)))
seat=stage.GetPrimAtPath('/Asset/Collision/SourceMesh3')
mat,_=UsdShade.MaterialBindingAPI(seat).ComputeBoundMaterial(materialPurpose='physics')
seat_snapshot=dict(prim=str(seat.GetPath()),active=seat.IsActive(),effective_visibility=str(UsdGeom.Imageable(seat).ComputeVisibility()),
 purpose=UsdGeom.Imageable(seat).ComputePurpose(),world_row_matrix=np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(seat)),
 physics_and_physx_attributes={k:v for k,v in attrs(seat).items() if k.startswith(('physics:','physx'))},
 material_path=str(mat.GetPath()) if mat else None,material_attributes=attrs(mat.GetPrim()) if mat else None,
 static_body_in_USD=not seat.HasAPI(UsdPhysics.RigidBodyAPI),composed_stage_unit=UsdGeom.GetStageMetersPerUnit(stage),composed_up_axis=str(UsdGeom.GetStageUpAxis(stage)))
write('original_A_seat_composed_USD_snapshot.json',seat_snapshot)
comparisons=[]
for run in RUNS:
 cfg=yaml.safe_load((run/'episode_0000/config.yaml').read_text());score=json.loads((run/'episode_0000/result.json').read_text());bb=json.loads((run/'geometry_audit.json').read_text())['binding']['files']
 checks=dict(identical_physics_dictionary=cfg['physics']==cfg0['physics'],identical_adapter_dictionary=cfg['adapter']==cfg0['adapter'],
  identical_instrument_asset_directory=cfg['asset_directory']==cfg0['asset_directory'],identical_provenance_instrument=cfg['source']['instrument']==cfg0['source']['instrument'],
  identical_instrument_world_position=cfg['scene']['instrument_xyz_m']==cfg0['scene']['instrument_xyz_m'],identical_instrument_world_yaw=cfg['scene']['instrument_yaw_deg']==cfg0['scene']['instrument_yaw_deg'],
  identical_rack_dictionary=cfg['rack']==cfg0['rack'],same_original_instrument_dependency_hashes=all(bb.get(x['path'])==x['current_sha256'] for x in layers))
 comparisons.append(dict(run=run.relative_to(ROOT).as_posix(),config_sha256=sha(run/'episode_0000/config.yaml'),checks=checks,
  intentionally_changed_loading_offset_local_m=cfg.get('geometry',{}).get('target_loading_offset_local_m'),
  result={k:score.get(k) for k in ('episode_id','asset_id','task_type','task_success','full_success','record_valid','failure_type','termination_reason','simulation_seconds','grasp_success','transport_success','loading_sequence_observed','release_observed','retreat_observed','stable_after_retreat','grasp_relative_pose','physics_quality_flags')}))
source=ROOT/'assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda'
src=Usd.Stage.Open(str(source));reference=read_geometry(src);ref_material=integrate_material(reference['/Asset/Visual/Mesh']['body_points'],reference['/Asset/Visual/Mesh']['faces'])
registry_path=ROOT/'assets/lab_cuvette_loading/Size_v1/registry.json';registry=json.loads(registry_path.read_text());rows=[]
for ident,record in sorted(registry['assets'].items()):
 path=ROOT/record['asset_path'];current=Usd.Stage.Open(str(path));actual=read_geometry(current);S=np.array(record['axis_scale']);error=0.;zerror=0.;top=True;settings=True
 for prim,g in reference.items():
  other=actual[prim];error=max(error,float(np.abs(other['body_points']-g['body_points']*S).max()));zerror=max(zerror,float(np.abs(other['body_points'][:,2]-g['body_points'][:,2]).max()));top&=np.array_equal(g['faces'],other['faces'])
  a,b=attrs(src.GetPrimAtPath(prim)),attrs(current.GetPrimAtPath(prim));settings&=all(a[k]==b[k] for k in a if k not in {'points','extent'})
 visual=actual['/Asset/Visual/Mesh'];mass=integrate_material(visual['body_points'],visual['faces']);written=usd_mass_snapshot(current)
 material_ok=all(attrs(p)==attrs(current.GetPrimAtPath(str(p.GetPath()))) for p in src.Traverse() if p.IsA(UsdShade.Material) or p.IsA(UsdShade.Shader))
 rows.append(dict(asset_id=ident,nominal_width_mm=record['nominal_outer_xy_mm'][0],asset_sha256=sha(path),hash_matches_registry=sha(path)==record['asset_sha256'],independent_json_matches_registry=json.loads(path.with_suffix('.json').read_text())==record,
  same_XY_affine_all_visual_and_collision=error<1e-8,maximum_vertex_storage_delta_m=error,Z_all_vertices_unchanged=zerror<1e-14,
  topology_unchanged=bool(top),all_other_mesh_attributes_unchanged=bool(settings),all_material_shader_attributes_unchanged=bool(material_ok),
  one_visual_plus28_collision=len(actual)==29 and sum(x['collision'] for x in actual.values())==28,
  height_actual_mm=float(np.ptp(visual['body_points'][:,2])*1000),bottom_origin_zero=abs(visual['body_points'][:,2].min())<1e-14,
  mass20g_retained=abs(written['mass_kg']-.020)<1e-8,reintegrated_COM_matches_USD=bool(np.allclose(mass['com_body_m'],written['com_body_m'],atol=2e-9,rtol=2e-6)),
  reintegrated_full_inertia_matches_USD=bool(np.allclose(mass['inertia_body_kg_m2'],written['inertia_body_kg_m2'],atol=2e-12,rtol=2e-6)),
  volume_follows_XY_area_scale=bool(np.isclose(mass['material_volume_m3'],ref_material['material_volume_m3']*S[0]*S[1],rtol=3e-6,atol=1e-13)),
  units_Zup_defaultPrim_preserved=UsdGeom.GetStageMetersPerUnit(current)==1 and str(UsdGeom.GetStageUpAxis(current))=='Z' and str(current.GetDefaultPrim().GetPath())=='/Asset',
  standalone_no_external_layers=len(current.GetUsedLayers())==2))
with (OUT/'all35_asset_checks.csv').open('x',newline='',encoding='utf-8') as f:
 writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
# Compare historical baseline JSON/YAML/CSV only; avoid rehashing large ignored media.
old=json.loads((ROOT/'docs/lab_cuvette_loading/Env_v1/results_20261021/report_evidence.json').read_text());historical=[]
for item in old.get('source_files',[]):
 p=ROOT/item['path']
 if item['path'].startswith('outputs/lab_cuvette_loading/Env_v1/') and p.suffix in ('.json','.yaml','.csv') and item.get('sha256'):
  historical.append(dict(path=item['path'],exists=p.is_file(),same_sha256=p.is_file() and sha(p)==item['sha256']))
old_paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
protected=[p for p in old_paths if p.startswith(('assets/lab_cuvette_loading/V0','config/lab_cuvette_loading/V0','demos/lab_cuvette_demo04/'))]
changed=subprocess.check_output(['git','diff',BASE,'--name-only','--',*protected],cwd=ROOT,text=True).splitlines()
boolean_keys=[k for k,v in rows[0].items() if isinstance(v,bool)]
checks={k:all(r[k] for r in rows) for k in boolean_keys}
result=dict(schema='labsim.Size_v1.protection_audit.v1',baseline_Env_v1_commit=subprocess.check_output(['git','rev-parse',BASE],cwd=ROOT,text=True).strip(),
 actual_audit_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 original_instrument_USD_dependency_count=len(layers),instrument_USD_dependencies=layers,original_A_seat_snapshot='original_A_seat_composed_USD_snapshot.json',
 Env_v1_to_Size_v1_runtime_config_comparisons=comparisons,source12_5mm_sha256=sha(source),source12_5mm_matches_preserved_sha256=sha(source)=='8d52757227303edd4f38918ee04763481f08846fdd8daa6803295c8fc77c689d',
 registry_sha256=sha(registry_path),registered_variant_count=len(rows),all35_checks=checks,maximum_observed_affine_vertex_storage_error_m=max(r['maximum_vertex_storage_delta_m'] for r in rows),
 historical_protected_tracked_paths=len(protected),historical_changed_paths=changed,historical_Env_v1_small_evidence=historical,
 local_main_sha=subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip(),
 geometry_range=dict(maximum_sampled_positive_conservative_path_certificate_mm=10.7,full_path_not_certified_mm=[10.72,11.0],largest_sampled_entrance_domain_present_mm=11.0,smallest_sampled_four_upright_yaw_entrance_rejected_mm=11.02),
 physical_scope='10.00mm complete success observed once and10.50mm complete task false withGRASP_SLIP; not a continuous physical width range.10.50mm release/retreat/final stability still observed, so do not call it proven geometric insertion blockage.',
 limitations=['Authored/composed USD layers and actual saved runtime parameter dictionaries were verified; no full attached cookedPxShape vertex equivalence across historical runs is claimed.',
 'This offline process starts neitherSimulationApp norGPU and does not step the formal verification running in parallel.',
 'Historical ignored large media/HDF5 were not all globally hashed before/after; small historical evidence hashes and tracked version files were checked.',
 'No real mass/material/robot dynamics calibration. Geometry certificates do not establish a continuous physical success interval.'])
write('protection_audit.json',result)
print(json.dumps({'variants':len(rows),'allchecks':checks,'layers':len(layers),'old_changed':changed,'old_evidence_mismatch':[x for x in historical if not x['same_sha256']]}))
