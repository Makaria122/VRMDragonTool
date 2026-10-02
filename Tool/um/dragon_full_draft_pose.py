"""Private offline multi-pose edge-strain screen; never certifies in-game motion."""
import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dragon_finger_metrics import finger_edges, summarize_ratios


def addon(folder):
    package=folder/'yk_gmd_blender'
    spec=importlib.util.spec_from_file_location('yk_gmd_blender',package/'__init__.py',
                                                submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec)
    sys.modules['yk_gmd_blender']=module
    spec.loader.exec_module(module)
    module.register()


def positions(obj):
    dg=bpy.context.evaluated_depsgraph_get()
    copy=obj.evaluated_get(dg).to_mesh()
    try:
        if len(copy.vertices)!=len(obj.data.vertices):raise RuntimeError('Evaluated topology changed')
        return [obj.matrix_world @ v.co for v in copy.vertices]
    finally:obj.evaluated_get(dg).to_mesh_clear()


def run(job,action_blend):
    addon(Path(job['addon']))
    # Do not rely on viewport selection: unselectable scene objects (for example,
    # helper meshes in source_reference.blend) survive bpy.ops.object.delete and
    # contaminate the imported GMD mesh-count validation.
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if bpy.ops.import_scene.gmd_skinned(filepath=job['working_copy'],strict=True,
                                         import_materials=True,import_hierarchy=True,
                                         import_objects=True)!={'FINISHED'}:
        raise RuntimeError('Strict import failed')
    scene=bpy.context.scene
    rig=next(o for o in scene.objects if o.type=='ARMATURE')
    meshes=[o for o in scene.objects if o.type=='MESH']
    if len(rig.data.bones)!=job.get('target_bone_count',358) or len(meshes)!=len(job['meshes']):
        raise RuntimeError(f'Invalid region for motion sample: bones={len(rig.data.bones)} '
                           f'expected={job.get("target_bone_count",358)}; meshes={len(meshes)} '
                           f'expected={len(job["meshes"])}')
    scene.frame_set(0)
    base={o.name:positions(o) for o in meshes}
    edges={o.name:[(e.vertices[0],e.vertices[1]) for e in o.data.edges] for o in meshes}
    finger_by_mesh={o.name:[(a,b,key,(base[o.name][a]-base[o.name][b]).length)
        for a,b,key in finger_edges(o) if (base[o.name][a]-base[o.name][b]).length>=.001]
        for o in meshes}
    finger_ratios={}
    with bpy.data.libraries.load(str(action_blend),link=False) as (source,target):
        names=[s for s in source.actions if s.startswith('p_yag_btl_')]
        if not names:raise RuntimeError('No owned combat sample actions')
        target.actions=names
    samples=[]
    for action in target.actions:
        rig.animation_data_create()
        rig.animation_data.action=action
        slots=[slot for slot in action.slots if slot.target_id_type=='OBJECT']
        if len(slots)!=1:
            raise RuntimeError(f'Expected exactly one armature action slot: {action.name}')
        rig.animation_data.action_slot=slots[0]
        if rig.animation_data.action_slot is None:
            raise RuntimeError(f'Animation slot did not bind to target rig: {action.name}')
        frame0,frame1=map(int,action.frame_range)
        for frame in sorted({frame0,(frame0+frame1)//2,frame1}):
            scene.frame_set(frame)
            for obj in meshes:
                moved=positions(obj)
                before=base[obj.name]
                if any(not all(math.isfinite(c) for c in v) for v in moved):
                    raise RuntimeError(f'Nonfinite pose in {obj.name}')
                ratios=[]
                for a,b in edges[obj.name]:
                    old=(before[a]-before[b]).length
                    if old>1e-5:ratios.append((moved[a]-moved[b]).length/old)
                ratios.sort()
                if not ratios:raise RuntimeError('No nonzero edges')
                for a,b,key,old in finger_by_mesh[obj.name]:
                    finger_ratios.setdefault(key,[]).append((moved[a]-moved[b]).length/old)
                samples.append({'action':action.name,'frame':frame,'mesh':obj.name,
                                'max_edge_stretch':ratios[-1],
                                'p95_edge_stretch':ratios[int(.95*(len(ratios)-1))],
                                'max_vertex_move_m':max((a-b).length for a,b in zip(before,moved))})
    return {'region':job['region'],'action_count':len(target.actions),'sample_count':len(samples),
            'samples':samples,'max_edge_stretch':max(s['max_edge_stretch'] for s in samples),
            'motion_review_required':any(s['max_edge_stretch']>1.5 for s in samples),
            'finger_diagnostics':summarize_ratios(finger_ratios),
            'poses_evaluated_offline':True,'game_animation_validated':False,
            'game_install_changed':False}


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=3:raise SystemExit('expected -- job.json private_action.blend NEW_report.json')
    result=run(json.loads(Path(args[0]).read_text(encoding='utf-8')),Path(args[1]))
    with Path(args[2]).open('x',encoding='utf-8') as out:
        json.dump(result,out,ensure_ascii=False,indent=2)
        out.write('\n')
    print('DRAGON_FULL_DRAFT_POSE_SCREEN_OK',result['region'],result['max_edge_stretch'])
