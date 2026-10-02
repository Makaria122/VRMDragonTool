"""Read-only inventory + tentative region proposal for arbitrary VRM spatial previews.

Regions are editable suggestions; ambiguous meshes must be explicitly assigned
before any offline candidate export. Never writes scene or game files.
"""
import json
import re
import sys
from pathlib import Path


def propose(name, materials, minimum, neck_z):
    label=name.removeprefix('PREVIEW_ONLY_').casefold()
    mats=' '.join(materials).casefold()
    if any(word in label for word in ('tail','尻尾')):
        return 'tops', 'tail follows body outfit'
    if (any(word in label for word in ('hair','katyusha','headband','headset','髪','耳','帽子','髪飾'))
            or re.search(r'(?<![a-z])(?:ears?|hat|cap)(?![a-z])',label)):
        return 'hair', 'head/hair name'
    if any(word in label for word in ('eye','face','eyebrow','lash','mouth','瞳','顔','まつげ')):
        return 'face', 'face name'
    if label in ('body','head','素顔') and minimum>neck_z-.12:
        return 'face', 'body mesh entirely above neck'
    if 'hair' in mats and minimum>neck_z-.25:
        return 'hair', 'hair material near head'
    if minimum>neck_z-.05 and 'costume' in mats:
        return None, 'head accessory with costume material: choose hair or tops'
    return 'tops', 'body/outfit below head'


def run(mapping):
    import bpy
    rig_candidates=[o for o in bpy.data.objects if o.type=='ARMATURE' and o.name.startswith('PREVIEW_ONLY_')]
    if len(rig_candidates)!=1:
        raise RuntimeError('Expected exactly one private spatial-preview rig')
    rig=rig_candidates[0]
    target_prefix=mapping.get('target_rig_prefix')
    target=next((o for o in bpy.data.objects if o.type=='ARMATURE' and target_prefix
                 and o.name.startswith(target_prefix) and 'kubi_c_n' in o.data.bones),None)
    if target is None:raise RuntimeError('Missing selected original target reference')
    neck_z=(target.matrix_world @ target.data.bones['kubi_c_n'].head_local).z
    expected={x['source_bone'] for x in mapping['fit_plan']['matched_roles']}
    expected|={x['source_group'] for x in mapping['fit_plan']['accessory_parent_hints']}
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from dragon_ground_measurement import foot_weighted_minimum, support_floor
    foot_roles=('leftFoot','rightFoot','leftToes','rightToes')
    foot_map=[x for x in mapping['fit_plan']['matched_roles'] if x['role'] in foot_roles]
    source_foot_groups={x['source_bone'] for x in foot_map}
    target_foot_groups={x['target_bone'] for x in foot_map}
    def foot_minimum(obj, groups):
        vertices=(((obj.matrix_world@v.co).z,
            {obj.vertex_groups[w.group].name:w.weight for w in v.groups}) for v in obj.data.vertices)
        return foot_weighted_minimum(vertices,foot_groups=groups)
    rows=[]
    for o in sorted(bpy.data.objects,key=lambda obj:obj.name):
        if o.type!='MESH' or o.find_armature()!=rig:continue
        if not o.data.uv_layers:
            raise RuntimeError(f'UV missing in source VRM: {o.name}')
        z=[(o.matrix_world@v.co).z for v in o.data.vertices]
        names=[m.name if m else '' for m in o.data.materials]
        region,reason=propose(o.name,names,min(z),neck_z)
        used={o.vertex_groups[w.group].name for v in o.data.vertices for w in v.groups if w.weight>1e-8}
        unknown=sorted(used-expected)
        rows.append({'object':o.name,'vertices':len(o.data.vertices),'faces':len(o.data.polygons),
                     'materials':names,'min_z_m':round(min(z),4),'max_z_m':round(max(z),4),
                     'shape_keys':len(o.data.shape_keys.key_blocks) if o.data.shape_keys else 0,
                     'foot_weighted_min_z_m':foot_minimum(o,source_foot_groups),
                     'region':region,'reason':reason,'unknown_weight_groups':unknown,
                     'unweighted_vertices':sum(not v.groups for v in o.data.vertices)})
    if not rows:raise RuntimeError('No skinned VRM meshes in spatial preview')
    source_ankles=[x['source_bone'] for x in foot_map if x['role'] in ('leftFoot','rightFoot')]
    target_ankles=[x['target_bone'] for x in foot_map if x['role'] in ('leftFoot','rightFoot')]
    if len(source_ankles)!=2 or len(target_ankles)!=2:
        raise RuntimeError('Both foot anchors are required for support measurement')
    source_ankle_z=sum((rig.matrix_world@rig.data.bones[n].head_local).z for n in source_ankles)/2
    target_ankle_z=sum((target.matrix_world@target.data.bones[n].head_local).z for n in target_ankles)/2
    source_floor,source_floor_meshes=support_floor(
        [(row['object'],row['foot_weighted_min_z_m']) for row in rows],source_ankle_z,'source')
    target_meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.find_armature()==target]
    if not target_meshes:raise RuntimeError('Target reference has no skinned meshes for ground measurement')
    target_floor,target_floor_meshes=support_floor(
        [(o.name,foot_minimum(o,target_foot_groups)) for o in target_meshes],target_ankle_z,'target')
    ground_alignment={'source_floor_m':round(source_floor,5),
                      'source_floor_meshes':source_floor_meshes,
                      'target_floor_meshes':target_floor_meshes,
                      'target_floor_m':round(target_floor,5),
                      'measured_correction_m':round(target_floor-source_floor,5),
                      'basis':'foot-support-weights-v2: foot/toe weight >=25%, below ankle; minimum support vertices'}
    source_roles={x['role']:x for x in mapping['fit_plan']['matched_roles']}
    joint_anchors={}
    for role,item in source_roles.items():
        if item['source_bone'] in rig.data.bones and item['target_bone'] in target.data.bones:
            joint_anchors[role]={'source_bone':item['source_bone'],'target_bone':item['target_bone'],
                'source':list(rig.matrix_world@rig.data.bones[item['source_bone']].head_local),
                'target':list(target.matrix_world@target.data.bones[item['target_bone']].head_local)}
    foot_alignment=[]
    for role in ('leftLowerLeg','rightLowerLeg','leftFoot','rightFoot'):
        item=source_roles.get(role)
        if not item or item['source_bone'] not in rig.data.bones or item['target_bone'] not in target.data.bones:
            continue
        source_head=rig.matrix_world@rig.data.bones[item['source_bone']].head_local
        target_head=target.matrix_world@target.data.bones[item['target_bone']].head_local
        delta=target_head-source_head
        foot_alignment.append({'role':role,'source_bone':item['source_bone'],
            'target_bone':item['target_bone'],'delta_m':[round(c,6) for c in delta],
            'distance_m':round(delta.length,6)})
    return {'schema_version':1,'source_rig':rig.name,'neck_z_m':neck_z,'meshes':rows,
            'ground_alignment':ground_alignment,'foot_alignment':foot_alignment,
            'joint_anchors':joint_anchors,
            'mesh_count':len(rows),'ambiguous_meshes':[row['object'] for row in rows if row['region'] is None],
            'unknown_weight_groups':sorted({name for row in rows for name in row['unknown_weight_groups']}),
            'full_avatar_converted':False,'requires_region_review':True,'game_install_changed':False}


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=2:raise SystemExit('expected -- mapping.json inventory.json')
    mapping=json.loads(Path(args[0]).read_text(encoding='utf-8'))
    report=run(mapping)
    with Path(args[1]).open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('DRAGON_GENERIC_INVENTORY_OK',report['mesh_count'],len(report['ambiguous_meshes']))
