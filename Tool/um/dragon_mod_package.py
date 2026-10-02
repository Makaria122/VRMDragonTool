"""Package an offline candidate in Lost Judgment Mods folder format."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

STEMS = {'tops': 'c_cl_x_yagami', 'face': 'c_cl_f_yagami', 'hair': 'c_cl_h_yagami'}


class ModPackageError(ValueError):
    pass


def _safe_out(path: Path) -> None:
    names={part.lower() for part in path.parts}
    program=Path(__file__).resolve().parents[1]
    bundle=program.parent if (program.parent/'Blender'/'blender.exe').is_file() else program
    from um.dragon_beta import portable_data_path
    if ('mods' in names or {'steamapps','common'}<=names
            or (path.is_relative_to(bundle) and not portable_data_path(path,bundle))):
        raise ModPackageError('Select a NEW output parent outside game, Tool, repository and mods folders')


def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def combine_mod_folders(sources: list[str | Path], output_root: str | Path,
                        title: str) -> dict:
    """Merge already-built local mods, accepting only byte-identical path collisions.

    Inputs are read-only. Output is a new private Mods-format folder, never installed.
    """
    source_paths=[Path(p).expanduser().resolve(strict=True) for p in sources]
    output=Path(output_root).expanduser().resolve()
    if len(source_paths)<2 or len({str(p).casefold() for p in source_paths})!=len(source_paths):
        raise ModPackageError('Select at least two distinct existing mod folders')
    if output.exists() or not output.parent.is_dir():
        raise ModPackageError('Choose a new output folder under an existing private parent')
    _safe_out(output)
    label=title.strip()
    if not label or len(label)>60 or '\n' in label or '\r' in label:
        raise ModPackageError('Choose a one-line combined mod title (1-60 characters)')
    slug=re.sub(r'[^a-z0-9_-]+','_',label.casefold()).strip('_')[:40] or 'vrm_combined'

    # Validate all sources and detect Windows case-insensitive path collisions before writing.
    files={}
    source_summaries=[]
    for source in source_paths:
        if not source.is_dir() or not (source/'mod-meta.yaml').is_file():
            raise ModPackageError(f'Not a mod folder with mod-meta.yaml: {source.name}')
        count=0
        for path in source.rglob('*'):
            if path.is_symlink():
                raise ModPackageError(f'Symbolic links are not supported: {path.name}')
            if not path.is_file():
                continue
            relative=path.relative_to(source)
            if relative.as_posix().casefold() in ('mod-meta.yaml','modlog.md'):
                continue
            if any(part in ('..','') for part in relative.parts) or relative.is_absolute():
                raise ModPackageError(f'Unsafe relative path in source mod: {relative}')
            key=relative.as_posix().casefold()
            digest=_sha256(path)
            previous=files.get(key)
            if previous and previous['sha256']!=digest:
                raise ModPackageError(
                    f'Incompatible mods: different files collide at {relative.as_posix()} '
                    f'({previous["source_name"]} vs {source.name})')
            if previous is None:
                files[key]={'source':path,'relative':relative,'sha256':digest,
                            'source_name':source.name}
            count+=1
        if count==0:
            raise ModPackageError(f'Mod folder has no payload files: {source.name}')
        source_summaries.append({'name':source.name,'payload_file_count':count})

    destination=output/'Mods'/slug
    try:
        destination.mkdir(parents=True)
        for item in files.values():
            target=destination/item['relative']
            target.parent.mkdir(parents=True,exist_ok=True)
            with item['source'].open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src,dst)
            if _sha256(target)!=item['sha256']:
                raise IOError(f'Hash mismatch while copying {item["relative"]}')
        metadata=(f'Name: {json.dumps(label+" (combined beta)",ensure_ascii=False)}\n'
                  'Author: "Local personal mod"\nVersion: "0.0.0-beta"\n'
                  'Description: "Merged local mods; inspect combine-status.json before use."\n')
        (destination/'mod-meta.yaml').write_text(metadata,encoding='utf-8')
        logs=['# Combined local mod package','',
              '- This package only combines paths; it does not validate appearance or gameplay.',
              '- No game installation was changed.','', '## Inputs']
        logs.extend(f'- `{row["name"]}`' for row in source_summaries)
        (destination/'MODLOG.md').write_text('\n'.join(logs)+'\n',encoding='utf-8')
        manifest={'status':'MODS_COMBINED_UNVERIFIED','installed':False,
                  'game_install_changed':False,'sources':source_summaries,
                  'payload_files':len(files),'identical_collisions_deduplicated':sum(
                      row['payload_file_count'] for row in source_summaries)-len(files)}
        (output/'combine-status.json').write_text(
            json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except Exception:
        shutil.rmtree(output,ignore_errors=True)
        raise
    return {'status':'MODS_COMBINED_UNVERIFIED','installed':False,
            'game_install_changed':False,'mod_folder':str(destination),
            'source_count':len(source_paths),'payload_files':len(files)}


def package(candidate: str | Path, output_root: str | Path, title: str,
            target_id: str = 'yagami') -> dict:
    source=Path(candidate).expanduser().resolve(strict=True)
    output=Path(output_root).expanduser().resolve()
    if not source.is_dir() or output.exists() or not output.parent.is_dir():
        raise ModPackageError('Select an existing candidate and a NEW private output folder')
    _safe_out(output)
    from um.dragon_targets import get_target
    target=get_target(target_id)
    status=json.loads((source/'status.json').read_text(encoding='utf-8'))
    if (status.get('target_id', 'yagami')!=target_id
            or status.get('strict_reimport_regions')!=len(target.slots)
            or status.get('source_mesh_count',0)<len(target.slots)
            or status.get('game_install_changed') is not False):
        raise ModPackageError('Candidate lacks complete three-region strict reimport')
    files=[]
    for slot in target.slots:
        role,stem=slot.region,slot.stem
        gmd=source/'chara'/role/stem/(stem+'.gmd')
        if not gmd.is_file() or gmd.stat().st_size<128:
            raise ModPackageError(f'Missing strict-exported {role} GMD')
        files.append((gmd,Path('chara')/role/stem/gmd.name))
    textures=sorted((source/'chara'/'dds_hires'/'00').glob('*.dds'))
    def valid_dds(texture):
        with texture.open('rb') as stream:
            return stream.read(4)==b'DDS '
    if not textures or any(not valid_dds(texture) for texture in textures):
        raise ModPackageError('Candidate needs valid private DDS textures')
    files.extend((t,Path('chara/dds_hires/00')/t.name) for t in textures)
    label=title.strip()
    if not label or len(label)>60 or '\n' in label or '\r' in label:
        raise ModPackageError('Choose a one-line mod title (1-60 characters)')
    slug=re.sub(r'[^a-z0-9_-]+','_',label.casefold()).strip('_')[:40] or 'vrm_avatar'
    folder=output/'Mods'/slug
    folder.mkdir(parents=True)  # all input validation above; output did not exist
    for src,relative in files:
        dst=folder/relative
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst)
    verdict=status.get('status','UNKNOWN')
    metadata=(f'Name: {json.dumps(label+" (beta)",ensure_ascii=False)}\n'
              'Author: "Local personal mod"\n'
              'Version: "0.0.0-beta"\n'
              f'Description: {json.dumps("Validation status: "+verdict+". See MODLOG.md for test details.",ensure_ascii=False)}\n')
    (folder/'mod-meta.yaml').write_text(metadata,encoding='utf-8')
    log=source/'MODLOG.md'
    if log.is_file():
        shutil.copyfile(log,folder/'MODLOG.md')
    else:
        (folder/'MODLOG.md').write_text(f'# Private review package\n\n- Verdict: {verdict}. No game installation.\n',encoding='utf-8')
    (output/'status.json').write_text(json.dumps({'status':'MODS_FORMAT_READY',
        'source_verdict':verdict,'installed':False,'game_install_changed':False,
        'mod_folder':str(folder)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'status':'MODS_FORMAT_READY','target_id':target.id,'mod_folder':str(folder),
            'game_install_changed':False,'gmd_count':len(target.slots),'dds_count':len(textures)}
