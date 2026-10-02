"""Create a new, allowlisted source distribution; never push or copy private assets."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOP_FILES=('Start-Tool.cmd','.gitignore','README.md','LICENSE','THIRD_PARTY_NOTICES.md')
TOOL_FILES=('launch.py','export_public.py','README.md','CHANGELOG.md','requirements.txt')
SOURCE_TREES=('um','tests','prompts','vendor/yakuza-gmd-gmt-blender')
SUFFIXES={'.py','.md','.txt','.rst'}

def source_files(root=ROOT):
    root=Path(root).resolve();files=[]
    for name in TOP_FILES:
        files.append(root/name)
    for name in TOOL_FILES:
        files.append(root/'Tool'/name)
    for tree in SOURCE_TREES:
        for file in (root/'Tool'/tree).rglob('*'):
            if file.is_symlink() or not file.is_file():continue
            if any(x.startswith('.') or x=='__pycache__' for x in file.relative_to(root).parts):continue
            if not file.resolve().is_relative_to(root):raise ValueError('Source path escapes repository')
            if file.suffix.lower() in SUFFIXES or file.name in ('LICENSE','COPYING','NOTICE'):
                files.append(file)
    for file in files:
        if file.is_symlink() or not file.is_file():raise ValueError(f'Missing or unsafe source file: {file.name}')
        text=file.read_text(encoding='utf-8',errors='replace')
        if re.search(r'[A-Za-z]:[\\/]+Users[\\/]+(?!Public[\\/]|<)[^\s"\x27\\/]+',text):
            raise ValueError(f'Private absolute user path in {file.relative_to(root)}')
        if re.search(r'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):
            raise ValueError(f'Possible credential material in {file.relative_to(root)}')
    return sorted(set(files))

def export(output,root=ROOT):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Output already exists; choose a NEW folder')
    if output==root or output.is_relative_to(root/'Tool') or {'steamapps','common'} <= {x.lower() for x in output.parts} or 'mods' in {x.lower() for x in output.parts}:
        raise ValueError('Output must not be source Tool or a game/mod folder')
    files=source_files(root)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='public-export-',dir=output.parent) as t:
        stage=Path(t)/'source';stage.mkdir();manifest={}
        for file in files:
            relative=file.relative_to(root);destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,destination);manifest[relative.as_posix()]=hashlib.sha256(destination.read_bytes()).hexdigest()
        (stage/'public-manifest.json').write_text(json.dumps({'private_assets_included':False,'files':manifest},indent=2)+'\n',encoding='utf-8')
        stage.rename(output)
    return {'source_files':len(files),'output':str(output),'github_pushed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(export(parser.parse_args().output),ensure_ascii=False))
