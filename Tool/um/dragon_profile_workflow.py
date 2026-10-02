"""Standalone local-AI per-avatar profile preparation for the GUI profile tab."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from um.dragon import inspect_blender
from um.dragon_beta import _digest, _private
from um.dragon_local_profile import LocalProfileError, _validate, create as create_local


def profile_directory(vrm: str | Path, profile_root: str | Path, target_id: str = 'yagami') -> Path:
    vrm=Path(vrm).expanduser().resolve(strict=True)
    slug=re.sub(r'[^A-Za-z0-9_-]+','_',vrm.stem).strip('_')[:36] or 'avatar'
    root=Path(profile_root).expanduser().resolve()
    if target_id != 'yagami':
        root=root/target_id
    return root/f'{slug}_{_digest(vrm)[:12]}'


def role_mappings(fit_plan: dict) -> list[list[str]]:
    return sorted([[row['source_bone'],row['target_bone']]
                   for row in fit_plan['matched_roles']])


def reference_hashes(references: dict[str,str | Path]) -> dict:
    return {role:{'path':str(Path(path).expanduser().resolve(strict=True)),
                   'sha256':_digest(Path(path).expanduser().resolve(strict=True))}
            for role,path in sorted(references.items())}


def _blender(blender: Path, scene: Path, script: str, args: list[Path], progress) -> None:
    progress(f'Blender: {script}')
    command=[str(blender),'--background','--factory-startup','--python-exit-code','1',str(scene),
             '--python',str(Path(__file__).with_name(script)),'--',*(str(x) for x in args)]
    try:
        result=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=360)
    except subprocess.TimeoutExpired as exc:
        raise LocalProfileError(f'{script} timed out after 360 seconds') from exc
    if result.returncode or not args[-1].is_file():
        lines=(result.stderr+'\n'+result.stdout).splitlines()
        raise LocalProfileError(f'{script} failed: {chr(10).join(lines[-14:])[-2400:]}')


def create_avatar_profile(vrm: str | Path, references: dict[str,str | Path],
                          blender: str | Path, addon: str | Path,
                          profile_root: str | Path,
                          progress: Callable[[str],None] | None = None,
                          target_id: str = 'yagami') -> dict:
    progress=progress or (lambda message:None)
    vrm=Path(vrm).expanduser().resolve(strict=True)
    references={role:Path(references[role]).expanduser().resolve(strict=True)
                for role in ('tops','face','hair')}
    blender=Path(blender).expanduser().resolve(strict=True)
    addon=Path(addon).expanduser().resolve(strict=True)
    root=Path(profile_root).expanduser().resolve()
    program=Path(__file__).resolve().parents[1]
    bundle=program.parent if (program.parent/'Blender'/'blender.exe').is_file() else program
    for path in (vrm,*references.values(),root):
        _private(path,bundle)
    if root.exists() and not root.is_dir():
        raise LocalProfileError('Profile output root is not a directory')
    if not blender.is_file() or not (addon/'yk_gmd_blender'/'__init__.py').is_file():
        raise LocalProfileError('Select local Blender and the GMD addon')
    root.mkdir(parents=True,exist_ok=True)
    folder=profile_directory(vrm,root,target_id)
    folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output=folder/f'avatar-profile_{stamp}.json'
    fit_hashes=reference_hashes(references)
    progress('VRMとGMD参照を点検してプロファイル用データを準備中…')
    with tempfile.TemporaryDirectory(prefix='.profile_work_',dir=folder) as temp:
        work=Path(temp)
        workspace=work/'source.blend'
        mapping=inspect_blender(vrm,references['tops'],blender,addon,
                                references['face'],references['hair'],workspace=workspace,
                                target_id=target_id)
        mapping_file=work/'bone_map.json'
        mapping_file.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        alignment=work/'alignment.json'
        _blender(blender,workspace,'dragon_alignment_worker.py',[mapping_file,alignment],progress)
        preview=work/'spatial_preview.blend'
        _blender(blender,workspace,'dragon_alignment_preview.py',[alignment,preview],progress)
        inventory_file=work/'inventory.json'
        _blender(blender,preview,'dragon_generic_inventory.py',[mapping_file,inventory_file],progress)
        inventory=json.loads(inventory_file.read_text(encoding='utf-8'))
        if any(row.get('unweighted_vertices',0) for row in inventory.get('meshes',[])):
            raise LocalProfileError('Unweighted VRM vertices prevent a safe reusable profile')
        progress('ローカルOllamaでプロファイルを作成中…')
        # Keep partial AI output out of the reusable profile directory.
        profile=create_local(inventory,mapping['fit_plan'],work/'avatar-profile.json')
    profile.update({'source_vrm':str(vrm),'source_vrm_sha256':_digest(vrm),
                    'source_references':fit_hashes,
                    'source_mesh_names':sorted(row['object'] for row in inventory['meshes']),
                    'unknown_weight_groups':sorted(inventory.get('unknown_weight_groups',[])),
                    'source_role_mappings':role_mappings(mapping['fit_plan']),
                    'target_id':target_id,'profile_created_at':stamp})
    temporary=folder/f'.{output.name}.tmp'
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(profile,stream,ensure_ascii=False,indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        if output.exists():
            raise LocalProfileError('Profile output already exists')
        os.replace(temporary,output)
    finally:
        temporary.unlink(missing_ok=True)
    removed=0
    for previous in folder.glob('avatar-profile_*.json'):
        if previous == output:
            continue
        try:
            previous.unlink()
            removed+=1
        except OSError as exc:
            raise LocalProfileError(f'New profile saved, but old profile could not be removed: {previous}: {exc}') from exc
    return {'status':'AVATAR_PROFILE_CREATED','avatar_profile_path':str(output),
            'removed_old_profiles':removed,
            'profile_method':profile['profile_method'],'model':profile['model'],
            'mesh_count':len(profile['mesh_regions']),
            'ground_alignment':profile['ground_alignment'],
            'source_vrm_sha256':profile['source_vrm_sha256']}


def load_cached_profile(vrm: str | Path, references: dict[str,str | Path],
                        inventory: dict, fit_plan: dict, profile_root: str | Path,
                        target_id: str = 'yagami') -> dict | None:
    vrm=Path(vrm).expanduser().resolve(strict=True)
    folder=profile_directory(vrm,profile_root,target_id)
    candidates=sorted(folder.glob('avatar-profile_*.json'),key=lambda x:x.stat().st_mtime,reverse=True) if folder.is_dir() else []
    source_hash=_digest(vrm)
    hashes=reference_hashes(references)
    for path in candidates:
        try:
            profile=json.loads(path.read_text(encoding='utf-8'))
            if (profile.get('target_id', 'yagami')!=target_id
                    or profile.get('source_vrm_sha256')!=source_hash
                    or profile.get('source_references')!=hashes
                    or profile.get('source_role_mappings')!=role_mappings(fit_plan)):
                continue
            if set(profile.get('mesh_regions',{}))!={row['object'] for row in inventory['meshes']}:
                continue
            if inventory.get('joint_anchors'):
                from um.dragon_anatomical_fit import recipe
                # Recompute from current geometry, rejecting stale or tampered recipes.
                if profile.get('anatomical_fit')!=recipe(inventory):
                    continue
            ground=profile['ground_alignment']
            action=ground['local_ai_action']
            raw={'mesh_regions':profile['mesh_regions'],
                 'accessory_parent_hints':profile['accessory_parent_hints'],
                 'ground_action':action,
                 'foot_fit_targets':profile['foot_fit_targets']}
            _validate(raw,inventory,fit_plan)
            if set(profile['mesh_regions'].values())!={'tops','face','hair'}:
                continue
            return profile
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    return None
