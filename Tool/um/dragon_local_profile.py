"""Create a per-VRM mapping profile with an already-running local Ollama model.

Only compact mesh/bone labels and counts are sent to loopback. The model cannot
edit geometry; every returned label is checked against the local source inventory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

MODEL = os.environ.get('UM_DRAGON_LOCAL_MODEL', 'qwen2.5-coder:7b')


class LocalProfileError(ValueError):
    pass


def _expand_mesh_ids(data: dict, rows: list[dict]) -> dict:
    """Resolve compact model-facing IDs without accepting invented mesh names."""
    regions=data.get('mesh_regions') if isinstance(data,dict) else None
    if not isinstance(regions,dict):
        return data
    ids={f'm{index}':row['object'] for index,row in enumerate(rows)}
    if set(regions)==set(ids):
        return {**data,'mesh_regions':{ids[key]:value for key,value in regions.items()}}
    return data


def _validate(data: dict, inventory: dict, fit_plan: dict) -> dict:
    rows=inventory.get('meshes')
    if not isinstance(rows,list) or not rows:
        raise LocalProfileError('VRM inventory has no meshes')
    meshes={row['object']:row for row in rows}
    if len(meshes)!=len(rows):
        raise LocalProfileError('Duplicate VRM mesh names in inventory')
    matched={row['source_bone'] for row in fit_plan.get('matched_roles',[])}
    accessories={row['source_group'] for row in fit_plan.get('accessory_parent_hints',[])}
    unknown=set(inventory.get('unknown_weight_groups',[]))-matched-accessories
    allowed_targets={row['target_bone'] for row in fit_plan.get('matched_roles',[])}
    if not isinstance(data,dict) or set(data)!={'mesh_regions','accessory_parent_hints','ground_action','foot_fit_targets'}:
        raise LocalProfileError('Local AI profile has unexpected fields')
    regions=data['mesh_regions']
    if not isinstance(regions,dict) or set(regions)!=set(meshes):
        raise LocalProfileError('Local AI must classify every known mesh exactly once')
    if any(value not in ('tops','face','hair') for value in regions.values()):
        raise LocalProfileError('Local AI returned an unsupported mesh region')
    hints=data['accessory_parent_hints']
    if not isinstance(hints,list):
        raise LocalProfileError('Local AI accessory mappings must be a list')
    parsed={}
    for hint in hints:
        if not isinstance(hint,dict) or set(hint)!={'source_group','suggested_target'}:
            raise LocalProfileError('Invalid local AI bone mapping entry')
        source,target=hint['source_group'],hint['suggested_target']
        if source not in unknown or target not in allowed_targets or source in parsed:
            raise LocalProfileError('Local AI used an unknown source or target bone')
        parsed[source]=target
    if set(parsed)!=unknown:
        raise LocalProfileError('Local AI did not map every unmatched VRM weight group')
    ground=inventory.get('ground_alignment')
    if not isinstance(ground,dict) or type(ground.get('measured_correction_m')) not in (int,float):
        raise LocalProfileError('VRM/target floor measurements are missing')
    correction=float(ground['measured_correction_m'])
    action=data['ground_action']
    expected='raise' if correction>.005 else 'lower' if correction<-.005 else 'keep'
    if action!=expected:
        raise LocalProfileError('Local AI ground action disagrees with measured floor offset')
    recommended=max(-.25,min(.25,correction))
    foot_rows=inventory.get('foot_alignment',[])
    expected_foot_targets={row['target_bone'] for row in foot_rows
                           if .04<float(row.get('distance_m',0))<=.25}
    foot_targets=data['foot_fit_targets']
    if (not isinstance(foot_targets,list) or len(set(foot_targets))!=len(foot_targets)
            or set(foot_targets)!=expected_foot_targets):
        raise LocalProfileError('Local AI foot-fit list does not match bounded measured ankle/foot offsets')
    # Preserve the source order and report the model's decision beside the
    # deterministic inventory proposal so it is auditable/editable by the user.
    decisions=[]
    for name,row in meshes.items():
        decisions.append({'mesh':name,'region':regions[name],
                          'inventory_region':row.get('region'),'reason':row.get('reason','')})
    return {'schema':'dragon-avatar-profile/v1','model':MODEL,
            'profile_method':'local_ollama','mesh_regions':regions,
            'accessory_parent_hints':[{'source_group':source,'suggested_target':target}
                                      for source,target in sorted(parsed.items())],
            'mesh_decisions':decisions,
            'ground_alignment':{**ground,'local_ai_action':action,
                'recommended_vertical_offset_m':round(recommended,5),
                'applied_vertical_offset_m':0.0,
                'remaining_floor_delta_m':round(correction,5),
                'application_mode':'recommendation_only; global mesh translation is not applied'},
            'foot_fit_targets':sorted(expected_foot_targets),
            'foot_alignment':foot_rows,
            'game_install_changed':False}


def create(inventory: dict, fit_plan: dict, output: str | Path) -> dict:
    output=Path(output).expanduser().resolve()
    if output.exists():
        raise LocalProfileError('Per-VRM profile output already exists')
    rows=inventory.get('meshes',[])
    allowed=sorted({row['target_bone'] for row in fit_plan.get('matched_roles',[])})
    unknown=sorted(set(inventory.get('unknown_weight_groups',[]))-
                 {row['source_bone'] for row in fit_plan.get('matched_roles',[])}-
                 {row['source_group'] for row in fit_plan.get('accessory_parent_hints',[])})
    ground=inventory.get('ground_alignment')
    if not isinstance(ground,dict):
        raise LocalProfileError('Run spatial inventory with target floor measurements first')
    compact=[{'id':f'm{index}','name':row['object'],'materials':row.get('materials',[]),
              'vertices':row.get('vertices'),'faces':row.get('faces'),
              'height_range_m':[row.get('min_z_m'),row.get('max_z_m')],
              'deterministic_region':row.get('region'),'reason':row.get('reason','')}
             for index,row in enumerate(rows)]
    prompt=('Create a per-avatar Lost Judgment asset profile. Assign each VRM mesh ID to exactly one '
             'region: tops, face, or hair, using names/materials/height and deterministic hints. '
             'Preserve strong deterministic hints; ensure every region is represented when the inventory '
             'contains a candidate for it. A mesh explicitly described as entirely above the neck is face. '
             'Map every unknown source weight group to the closest semantically appropriate EXISTING '
             'target bone. Allowed target bones: '+json.dumps(allowed,ensure_ascii=False)+
             '. Unknown source groups: '+json.dumps(unknown,ensure_ascii=False)+
             '. Do not invent names. Do not propose geometry edits. Use only short m0, m1, ... IDs '
             'as mesh_regions keys, never mesh names; include every ID exactly once. Output JSON with exactly '
             'mesh_regions (mesh-ID to region), accessory_parent_hints '
             '([{source_group,suggested_target}]) and ground_action (raise/lower/keep). '
             'Foot correction targets are calculated deterministically, not proposed by the model. '
             'Ground measurements: '+json.dumps(ground,ensure_ascii=False)+'. Choose raise for a positive '
             'measured correction, lower for negative, otherwise keep. Mesh inventory: '
             +json.dumps(compact,ensure_ascii=False))
    mesh_ids=[f'm{index}' for index in range(len(rows))]
    response_schema={'type':'object','additionalProperties':False,
        'required':['mesh_regions','accessory_parent_hints','ground_action'],
        'properties':{
            'mesh_regions':{'type':'object','additionalProperties':False,'required':mesh_ids,
                'properties':{key:{'type':'string','enum':['tops','face','hair']} for key in mesh_ids}},
            'accessory_parent_hints':{'type':'array','minItems':len(unknown),'maxItems':len(unknown),
                'items':{'type':'object','additionalProperties':False,
                    'required':['source_group','suggested_target'],
                    'properties':{'source_group':{'type':'string','enum':unknown or ['UNUSED']},
                                  'suggested_target':{'type':'string','enum':allowed}}}},
            'ground_action':{'type':'string','enum':[
                'raise' if ground['measured_correction_m']>.005 else
                'lower' if ground['measured_correction_m']<-.005 else 'keep']}}}
    payload={'model':MODEL,'stream':False,'keep_alive':0,'format':response_schema,
        'messages':[{'role':'system','content':'Return only the requested compact JSON profile. No markdown.'},
                    {'role':'user','content':prompt}],
        'options':{'temperature':0,'num_predict':2400}}
    try:
        from um.dragon_local_ai import get_runtime
        runtime=get_runtime()
        runtime.setup()  # starts only the installed Tool-owned binary; no automatic download
        envelope=runtime.request('/api/chat',payload,timeout=120)
    except Exception as exc:
        raise LocalProfileError(f'Managed local Ollama unavailable: {exc}') from exc
    try:
        proposed=_expand_mesh_ids(json.loads(envelope['message']['content']),rows)
        if isinstance(proposed,dict):
            proposed['foot_fit_targets']=sorted(row['target_bone'] for row in inventory.get('foot_alignment',[])
                if .04<float(row.get('distance_m',0))<=.25)
        result=_validate(proposed,inventory,fit_plan)
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise LocalProfileError(f'Local Ollama returned invalid profile JSON: {exc}') from exc
    missing={'tops','face','hair'}-set(result['mesh_regions'].values())
    adjustments=[]
    for region in sorted(missing):
        candidates=[row for row in rows if row.get('region')==region]
        if not candidates:
            raise LocalProfileError(f'VRM inventory has no mesh candidate for required region: {region}')
        priority={'body mesh entirely above neck':0,'eye/face name':1,'face name':1,
                  'head/hair name':0,'hair material near head':1,'body/outfit below head':2}
        selected=min(candidates,key=lambda row:priority.get(row.get('reason',''),3))
        name=selected['object']
        previous=result['mesh_regions'][name]
        result['mesh_regions'][name]=region
        adjustments.append({'mesh':name,'from':previous,'to':region,
                            'reason':'ensured one candidate for each GMD region using deterministic inventory'})
    result['coverage_adjustments']=adjustments
    for decision in result['mesh_decisions']:
        decision['region']=result['mesh_regions'][decision['mesh']]
        if any(item['mesh']==decision['mesh'] for item in adjustments):
            decision['reason']+='; deterministic region coverage adjustment'
    if inventory.get('joint_anchors'):
        from um.dragon_anatomical_fit import recipe
        result['anatomical_fit']=recipe(inventory)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    return result
