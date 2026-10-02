"""One-button private VRM → Lost Judgment offline Mods-format review workflow.

Runs preflight, humanoid mapping, spatial alignment, DDS, mesh region inference,
strict GMD export/reimport and motion screen. NEVER installs into the game.
Even a completed Mods-format package is review-only until in-game validation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from um.dragon import inspect_blender
from um.dragon_beta import GENERIC_SCHEMA, REGIONS, _digest, _private, build
from um.dragon_mod_package import package
from um.dragon_textures import extract


class OneClickError(ValueError):
    pass


def _blender(blender: Path, scene: Path, script: str, arguments: list[Path], progress):
    target=Path(__file__).with_name(script)
    progress(f'Blender: {script}')
    cmd=[str(blender),'--background','--factory-startup','--python-exit-code','1',str(scene),
         '--python',str(target),'--',*(str(v) for v in arguments)]
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=360)
    except subprocess.TimeoutExpired as exc:
        raise OneClickError(f'{script}: 360秒でタイムアウト') from exc
    if proc.returncode or not arguments[-1].is_file():
        detail='\n'.join((proc.stderr+'\n'+proc.stdout).splitlines()[-22:])
        raise OneClickError(f'{script} failed: {detail[-3500:]}')


DUMMY_SOURCES={'texture_multi':'dummy_multi.dds','texture_normal':'dummy_nmap.dds',
               'texture_rt':'dummy_nmap.dds','texture_rd':'dummy_white.dds'}



def run(vrm: str | Path, references: dict[str,str | Path], blender: str | Path,
        addon: str | Path, action_blend: str | Path | None, baseline_report: str | Path | None,
        output: str | Path, dummy_texture_dir: str | Path | None,
        progress: Callable[[str],None] | None = None,
        target_id: str = 'yagami', profile_root: str | Path | None = None,
        preparation_cache: dict | None = None) -> dict:
    progress=progress or (lambda value: None)
    vrm=Path(vrm).expanduser().resolve(strict=True)
    blender=Path(blender).expanduser().resolve(strict=True)
    addon=Path(addon).expanduser().resolve(strict=True)
    action=Path(action_blend).expanduser().resolve(strict=True) if action_blend else None
    baseline=Path(baseline_report).expanduser().resolve(strict=True) if baseline_report else None
    from um.dragon_targets import get_target
    target=get_target(target_id)
    if dummy_texture_dir:
        dummy_dir=Path(dummy_texture_dir).expanduser().resolve(strict=True)
        dummy_files={key:(dummy_dir/name).resolve(strict=True) for key,name in DUMMY_SOURCES.items()}
        for path in dummy_files.values():
            with path.open('rb') as stream:
                if stream.read(4)!=b'DDS ':
                    raise OneClickError(f'Invalid dummy DDS: {path.name}')
    else:
        dummy_dir=None
        dummy_files={}
    refs={role:Path(references[role]).expanduser().resolve(strict=True) for role in REGIONS}
    output=Path(output).expanduser().resolve()
    program=Path(__file__).resolve().parents[1]
    bundle=program.parent if (program.parent/'Blender'/'blender.exe').is_file() else program
    for path in (vrm,*([action] if action else []),*([baseline] if baseline else []),*refs.values(),*([dummy_dir] if dummy_dir else []),output):
        _private(path,bundle)
    if output.exists() or not output.parent.is_dir():
        raise OneClickError('出力先はゲーム/ツール外の新規フォルダにしてください')
    if not blender.is_file() or not (addon/'yk_gmd_blender'/'__init__.py').is_file():
        raise OneClickError('ローカルBlenderとGMDアドオンが必要です')
    output.mkdir()
    if dummy_dir is None:
        from um.dragon_neutral_maps import write_neutral_maps
        neutral=write_neutral_maps(output/'neutral_maps')
        dummy_dir=output/'neutral_maps'
        dummy_files={'texture_multi':neutral['multi'],'texture_normal':neutral['normal'],
                     'texture_rt':neutral['normal'],'texture_rd':neutral['white']}
    status_path=output/'status.json'
    status_path.write_text(json.dumps({'status':'IN_PROGRESS','game_install_changed':False},indent=2)+'\n',encoding='utf-8')
    log=output/'MODLOG.md'
    log.write_text(f'# Private one-click VRM conversion\n\n- Target: {target.label} (`{target.id}`).\n'
                   f'- VRM: `{vrm.name}`.\n'
                   '- User-owned Lost Judgment references only; originals/game/installed MODs unchanged.\n'
                   '- Mods-format output and validation results are recorded locally.\n',encoding='utf-8')
    try:
        progress('VRMと元GMDを詳細点検中…')
        workspace=output/'source_reference.blend'
        if target_id == 'yagami':
            checked=inspect_blender(vrm,refs['tops'],blender,addon,refs['face'],refs['hair'],
                                    workspace=workspace)
            checked['target_id']='yagami'
            checked['target_bone_count']=target.bone_count
            checked['target_rig_prefix']=target.rig_prefix
        else:
            checked=inspect_blender(vrm,refs['tops'],blender,addon,refs['face'],refs['hair'],
                                    workspace=workspace,target_id=target_id)
        from um.dragon_skeleton_cache import measured_group, equivalent
        group_key,snapshots=measured_group(checked,_digest(vrm),target_id)
        shared=preparation_cache.get(group_key) if preparation_cache is not None else None
        if shared and (not equivalent(shared['snapshots'],snapshots)
                       or shared['fit_plan']!=checked['fit_plan']):
            shared=None
        if shared:
            checked['fit_plan']=copy.deepcopy(shared['fit_plan'])
            progress(f'骨格グループ一致: {shared["owner"]} の骨対応・位置合わせを再利用します')
        (output/'bone_map.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if action is not None and baseline is None:
            baseline=output/f'{target_id}_proxy_original_pose.json'
            ref_mesh_count=checked['blender_inspection']['references']['tops']['mesh_count']
            baseline_job={'region':'tops','working_copy':str(refs['tops']),'addon':str(addon),
                          'target_bone_count':target.bone_count,'meshes':[{} for _ in range(ref_mesh_count)]}
            baseline_job_path=output/f'{target_id}_baseline_job.json'
            baseline_job_path.write_text(json.dumps(baseline_job,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            _blender(blender,workspace,'dragon_full_draft_pose.py',
                     [baseline_job_path,action,baseline],progress)
        align=output/'alignment.json'
        if shared:
            alignment=copy.deepcopy(shared['alignment'])
            inspection=checked['blender_inspection']
            alignment['target_rig']=inspection['references']['tops']['rig_names'][0]
            avatar=inspection['vrm']
            alignment['source_rig']=max(zip(avatar['rig_names'],avatar['bone_counts']),key=lambda p:p[1])[0]
            align.write_text(json.dumps(alignment,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        else:
            _blender(blender,workspace,'dragon_alignment_worker.py',[output/'bone_map.json',align],progress)
        preview=output/'spatial_preview.blend'
        _blender(blender,workspace,'dragon_alignment_preview.py',[align,preview],progress)
        progress('VRMの画像を個人用DDSへ変換中…')
        textures=extract(vrm,output/'textures',target_id=target_id)
        # Dummy slots also live in a global game texture namespace. Isolate them
        # with the avatar textures and pass the exact names to the GMD worker.
        namespace=textures['texture_namespace']
        dummy_names={slot:f'{namespace}_' + {'texture_multi':'mt',
            'texture_normal':'nm','texture_rt':'nm','texture_rd':'wh'}[slot]+'.dds'
            for slot in DUMMY_SOURCES}
        # These four tiny user-owned game-compatible dummies replace only linked
        # shader maps per the checked Plan A v11 recipe; no assets are bundled.
        dds_dir=output/'textures'
        manifest_path=dds_dir/'texture-map.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for source_name,filename in sorted({src:dst for slot,src in DUMMY_SOURCES.items()
                                             for dst in (dummy_names[slot],)}.items()):
            source=dummy_dir/source_name
            dummy_target=dds_dir/filename
            shutil.copyfile(source,dummy_target)
            manifest['images'].append({'image_index':None,'filename':filename,
                'sha256':hashlib.sha256(dummy_target.read_bytes()).hexdigest(),'role':'game_dummy_map'})
        manifest['dummy_texture_slots']=dummy_names
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        inventory=output/'inventory.json'
        _blender(blender,preview,'dragon_generic_inventory.py',[output/'bone_map.json',inventory],progress)
        items=json.loads(inventory.read_text(encoding='utf-8'))
        if any(row['unweighted_vertices'] for row in items['meshes']):
            raise OneClickError('無ウェイト頂点があり、プロファイルだけでは安全に補完できません')
        from um.dragon_profile_workflow import load_cached_profile, reference_hashes, role_mappings
        profile_root=Path(profile_root).resolve() if profile_root is not None else output.parent.parent/'Profiles'
        if shared:
            from um.dragon_skeleton_cache import reuse_profile
            avatar_profile=reuse_profile(shared['profile'],items,checked['fit_plan'])
        else:
            avatar_profile=load_cached_profile(vrm,refs,items,checked['fit_plan'],profile_root,target_id)
        if avatar_profile:
            progress('既存の同一VRMプロフィールを再利用中…')
        else:
            progress('ローカルOllamaでこのVRM専用プロファイルを作成中…')
            from um.dragon_local_profile import create as create_local_profile
            avatar_profile=create_local_profile(items,checked['fit_plan'],output/'avatar-profile.json')
            avatar_profile['target_id']=target_id
            avatar_profile['source_vrm']=str(vrm)
            avatar_profile['source_vrm_sha256']=_digest(vrm)
            avatar_profile['source_references']=reference_hashes(refs)
            avatar_profile['source_mesh_names']=sorted(row['object'] for row in items['meshes'])
            avatar_profile['unknown_weight_groups']=sorted(items.get('unknown_weight_groups',[]))
            avatar_profile['source_role_mappings']=role_mappings(checked['fit_plan'])
        # Refresh provenance even when reusing another variant's classification.
        avatar_profile.update({'target_id':target_id,'source_vrm':str(vrm),
            'source_vrm_sha256':_digest(vrm),'source_references':reference_hashes(refs),
            'source_mesh_names':sorted(row['object'] for row in items['meshes']),
            'unknown_weight_groups':sorted(items.get('unknown_weight_groups',[])),
            'source_role_mappings':role_mappings(checked['fit_plan'])})
        # Ground alignment remains a measured recommendation, never a global translation.
        (output/'avatar-profile.json').write_text(json.dumps(avatar_profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        mapping=dict(checked['fit_plan'])
        mapping['accessory_parent_hints']=list(checked['fit_plan']['accessory_parent_hints'])+avatar_profile['accessory_parent_hints']
        for row in items['meshes']:
            row['region']=avatar_profile['mesh_regions'][row['object']]
            row['reason']=f'LOCAL_AI_PROFILE: {row["region"]}; {row.get("reason","")}'
        inventory.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if any(not any(row['region']==role for row in items['meshes']) for role in REGIONS):
            raise OneClickError('ローカルAIプロファイルに顔・髪・胴体すべての領域がありません')
        matmap={m['material_name'] for m in textures['materials']}
        unknown_mats={name for row in items['meshes'] for name in row['materials']
                      if re.sub(r'\.\d{3}$','',name) not in matmap}
        if unknown_mats:
            raise OneClickError(f'DDSに対応しないVRM材質: {sorted(unknown_mats)}')
        scale=json.loads(align.read_text(encoding='utf-8'))['uniform_scale']
        for slot in target.slots:
            role=slot.key
            combined_regions=set(slot.source_regions)
            job={'region':slot.region,'target_slot':role,'target_bone_count':target.bone_count,
                 'target_id':target_id,'source_regions':list(slot.source_regions),
                 'original_gmd':str(refs[slot.reference_role]),'working_copy':'UNBUILT_PRIVATE_CANDIDATE',
                 'addon':str(addon),'dds_dir':str(output/'textures'),
                 'texture_map':str(output/'textures'/'texture-map.json'),
                 'dummy_texture_slots':dummy_names,
                 'expected_source_scale':scale,'weight_smooth_iterations':0,
                 'matched_roles':mapping['matched_roles'],
                 'accessory_parent_hints':mapping['accessory_parent_hints'],
                 'anatomical_fit':avatar_profile.get('anatomical_fit'),
                 'foot_fit_targets':[] if avatar_profile.get('anatomical_fit') else avatar_profile['foot_fit_targets'],
                 'ground_alignment':avatar_profile['ground_alignment'],
                 'foot_joint_deltas':{row['target_bone']:row['delta_m'] for row in items.get('foot_alignment',[])
                                      if row['target_bone'] in avatar_profile['foot_fit_targets']},
                 'meshes':[{'object':row['object'],'blend':str(preview),'source_region':row['region']} for row in items['meshes']
                           if row['region'] in combined_regions]}
            (output/f'{role}_job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        profile={'schema':GENERIC_SCHEMA,'source_vrm':str(vrm),'vrm_sha256':_digest(vrm),
                 'template_dir':str(output),'action_blend':str(action) if action else None,
                 'original_pose_report':str(baseline) if baseline else None,'mesh_offsets':{},'target_id':target_id}
        profile_file=output/'beta-profile.json'
        profile_file.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        progress(f'{len(target.slots)}個の対象GMD候補を作成・再読込・オフライン動作で点検中…')
        candidate=build(profile_file,vrm,output/'Candidate',blender,addon,progress=progress)
        progress('ゲーム外のMods形式にまとめています（ゲームへの導入はしません）…')
        title=('VRM '+target.label+' '+vrm.stem)[:60]
        pack=package(output/'Candidate',output/'ReviewPack',title,target_id=target_id)
        foot_fit_applied={}
        anatomical_applied={}
        for slot in target.slots:
            role=slot.key
            result_file=output/'Candidate'/f'{role}_result.json'
            if result_file.is_file():
                staged=json.loads(result_file.read_text(encoding='utf-8')).get('staged',[])
                anatomical_applied.update({row['source']:row['anatomical_fit'] for row in staged
                    if row.get('anatomical_fit')})
                foot_fit_applied.update({row['source']:{'alpha':row.get('foot_fit_alpha',0.0),
                    'max_move_m':row.get('foot_fit_max_move_m',0.0),
                    'binding_edge':row.get('foot_fit_binding_edge'),
                    'floor':row.get('foot_fit_floor')} for row in staged
                    if row.get('foot_fit_max_move_m',0.0)>0})
        ground_report=dict(avatar_profile['ground_alignment'])
        fitted_floors=[anatomical_applied[name]['minimum_z_m']
            for name in ground_report.get('source_floor_meshes',[]) if name in anatomical_applied]
        if fitted_floors:
            ground_report['remaining_floor_delta_m']=round(ground_report['target_floor_m']-min(fitted_floors),6)
            ground_report['application_mode']='anatomical_rest_fit; no global mesh translation'
            ground_report['measurement_stage']='staged_rest_mesh; in-game contact unverified'
        report={'status':'MODS_FORMAT_READY','target_id':target.id,'target_label':target.label,
                'motion_validation_note':target.motion_note,'vrm':str(vrm),
                'private_output':str(output),'mod_folder':pack['mod_folder'],
                'candidate_status':candidate['status'],
                'motion_validation':candidate.get('motion_validation','RUN'),
                'motion_quality_passed':candidate.get('motion_quality_passed',False),
                'manual_review_required':True,
                'geometry_quality_passed':candidate.get('geometry_quality_passed',False),
                'blockers':candidate.get('blockers',[]),
                'avatar_profile':str(output/'avatar-profile.json'),
                'profile_method':avatar_profile['profile_method'],
                'skeleton_group':{'key':group_key,'reused':shared is not None,
                                  'owner':shared['owner'] if shared else target_id,
                                  'anatomical_recipe_reused':avatar_profile.get('anatomical_recipe_reused',False)}, 
                'adjustment_reuse':'alignment/AI labels and identical solver recipe; floor/foot measurements refreshed',
                'ground_alignment':ground_report,
                'foot_fit_targets':avatar_profile.get('foot_fit_targets',[]),
                'foot_fit_applied':foot_fit_applied,
                'anatomical_fit_applied':anatomical_applied,
                'game_install_changed':False,
                'pose_samples':candidate['pose_samples'],
                'finger_diagnostics':candidate.get('finger_diagnostics',{}),
                'auto_region_uncertain':avatar_profile.get('coverage_adjustments',[]),
                'geometry_warnings':candidate.get('geometry_warnings',[])}
        status_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with log.open('a',encoding='utf-8') as f:
            f.write(f'- Target: {target.label} (`{target.id}`); {len(target.slots)} strict GMD slot(s).\n'
                    f'- Motion note: {target.motion_note}\n'
                    f'- Strict roundtrip and {candidate["pose_samples"]} pose samples.\n'
                    f'- Validation: {candidate["status"]}; Mods-format output: {pack["mod_folder"]}.\n')
        if preparation_cache is not None and shared is None:
            preparation_cache[group_key]={'owner':target_id,'snapshots':snapshots,
                'fit_plan':copy.deepcopy(checked['fit_plan']),
                'alignment':json.loads(align.read_text(encoding='utf-8')),
                'profile':copy.deepcopy(avatar_profile)}
        return report
    except Exception as exc:
        status_path.write_text(json.dumps({'status':'BLOCKED_PIPELINE_ERROR',
            'error':str(exc),'private_output':str(output),
            'game_install_changed':False},
            ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with log.open('a',encoding='utf-8') as f:
            f.write('- Pipeline stopped; no game installation and no approved Mods output.\n')
        raise
