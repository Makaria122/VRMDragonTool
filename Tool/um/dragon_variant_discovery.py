"""Read-only discovery of approved character variant GMDs; output is private metadata only."""
from __future__ import annotations
import argparse, datetime, hashlib, json, re, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BLENDER=ROOT/'Tool'/'runtime'/'blender'/'blender.exe'
ADDON=ROOT/'Tool'/'vendor'/'yakuza-gmd-gmt-blender'
TARGETS={
 'yagami':('Yagami',('yagami',)), 'kaito':('Kaito',('kaito',)),
 'sugiura':('Fumiya Sugiura',('sugiura',)), 'tsukumo':('Makoto Tsukumo',('tsukumo',)),
 'saori':('Saori Shirosaki',('saori','ci01_saori')), 'higashi':('Toru Higashi',('higashi',)),
 'tesso':('Tesso',('tesso',)), 'kuwana':('Jin Kuwana',('kuwana',)), 'soma':('Kazuki Soma',('soma',)),
 'akutsu':('Daimu Akutsu',('akutsu',)), 'genda':('Ryuzo Genda',('genda',)),
 'hoshino':('Issei Hoshino',('hoshino',)), 'mafuyu':('Mafuyu Fujii',('mafuyu',)), 'sawa':('Yoko Sawa',('sawa',))}

def matching(model, aliases):
    tokens=re.split(r'[_/\\ .-]+',model.casefold())
    return any(alias in tokens for alias in aliases)

def qwen(character, candidates):
    payload={'character':character,'evidence':[{k:c.get(k) for k in ('source_relative_path','model_id','region','bone_count','bone_signature','rest_signature','shaders','scene_name','load_status','exclusion_reason')} for c in candidates]}
    prompt=('Review this compact local GMD metadata. Return ONLY JSON {"comments":["..."]}; '
       'comments are tentative observations, never declare compatibility guaranteed. Do not invent facts.\n'+json.dumps(payload,ensure_ascii=False))
    try:
        from um.dragon_local_ai import get_runtime
        runtime=get_runtime();runtime.setup()
        envelope=runtime.request('/api/generate',{'model':'qwen2.5-coder:7b','prompt':prompt,'stream':False,'keep_alive':0,'format':'json'},timeout=120)
        obj=json.loads(envelope.get('response',''))
        return obj.get('comments',[]) if isinstance(obj.get('comments',[]),list) else []
    except Exception as exc: return [f'Managed local Ollama unavailable/invalid response: {exc}']

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',type=Path,required=True); ap.add_argument('--blender',type=Path,default=BLENDER); ap.add_argument('--no-ollama',action='store_true'); args=ap.parse_args()
    source=args.source.resolve(); files=[]
    for p in source.rglob('*.gmd'):
        rel=p.relative_to(source); model=rel.parts[0] if len(rel.parts)>1 else p.stem
        hit=[key for key,(_,aliases) in TARGETS.items() if matching(model,aliases) or any(matching(part,aliases) for part in rel.parts)]
        if hit:
            region=next((part.casefold() for part in rel.parts[:-1] if part.casefold() in ('tops','face','hair')), 'other')
            files.append({'absolute_path':str(p.resolve()),'source_relative_path':rel.as_posix(),'model_id':model,'region':region,'file_size':p.stat().st_size,'target_ids':hit})
    timestamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); outdir=ROOT/'Tool'/'userdata'/'TargetDiscovery'; outdir.mkdir(parents=True,exist_ok=True)
    output=outdir/f'variant_inventory_{timestamp}.json'
    with tempfile.TemporaryDirectory(prefix='dragon_variant_') as td:
        job=Path(td)/'job.json'; workerout=Path(td)/'parsed.json'
        job.write_text(json.dumps({'addon':str(ADDON),'files':files,'output':str(workerout)}),encoding='utf8')
        if files and args.blender.is_file():
            proc=subprocess.run([str(args.blender),'--background','--factory-startup','--python',str(ROOT/'Tool'/'um'/'dragon_variant_worker.py'),'--',str(job)],capture_output=True,text=True,errors='replace',timeout=900)
            if workerout.exists(): parsed=json.loads(workerout.read_text(encoding='utf8'))
            else: parsed=[{'absolute_path':f['absolute_path'],'load_status':'failed','error':(proc.stderr+proc.stdout)[-3000:]} for f in files]
        else: parsed=[{'absolute_path':f['absolute_path'],'load_status':'not_inspected','error':'Blender unavailable'} for f in files]
    bypath={x['absolute_path']:x for x in parsed}; candidates=[]
    for f in files:
        d=dict(f); d.pop('target_ids'); meta=bypath.get(f['absolute_path'],{}); d.update({k:v for k,v in meta.items() if k!='absolute_path'})
        names=' '.join([d['model_id'],d['source_relative_path']]).casefold()
        reason=None
        if re.search(r'(^|[_/])(young|18|26|30|boy|child|chd|dead|ghost|test|dummy|chair|sit|naked)([_./]|$)',names): reason='Conservative exclusion: filename/model ID suggests young/dead/test/chair/sitting/naked special variant.'
        d['exclusion_reason']=reason
        d['bone_signature']=hashlib.sha256('\n'.join(d.get('bone_names',[])).encode()).hexdigest() if d.get('bone_names') else None
        d['rest_signature']=hashlib.sha256(json.dumps(d.get('rest_transforms',[]),separators=(',',':')).encode()).hexdigest() if d.get('rest_transforms') else None
        candidates.append(d)
    characters=[]
    for key,(label,aliases) in TARGETS.items():
        selected=[dict(c) for c in candidates if c['model_id'] in [x['model_id'] for x in files if key in x['target_ids']]]
        comments=qwen(label,selected) if selected and not args.no_ollama else (['Ollama analysis disabled.'] if args.no_ollama else [])
        characters.append({'target_id':key,'requested_name':label,'candidates':selected,'qwen_comments':comments})
    report={'schema_version':1,'generated_at_local':datetime.datetime.now().astimezone().isoformat(),'read_only':True,'source_root':str(source),'tool_root':str(ROOT),'method':{'parser':'Bundled yakuza-gmd-gmt-blender via Blender background strict import','blender_executable':str(args.blender),'full_candidate_count':len(files),'deep_inspected_count':sum(c.get('load_status') in ('loaded','failed') for c in candidates),'ollama_model':'qwen2.5-coder:7b','ollama_localhost_only':True},'characters':characters,'global_warnings':['AI comments are advisory only; compatibility is never guaranteed by model output.','No source binaries copied or modified; no game writes.'],'game_install_changed':False,'extracted_source_files_changed':False}
    with output.open('x',encoding='utf8') as f: json.dump(report,f,ensure_ascii=False,indent=2); f.write('\n')
    print(output); print(f'candidates={len(files)} inspected={report["method"]["deep_inspected_count"]}')
if __name__=='__main__': main()
