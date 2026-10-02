"""Read-only Blender worker for private GMD variant inventory."""
import importlib.util, json, sys, traceback
from pathlib import Path
import bpy


def load_addon(folder):
    package = Path(folder) / 'yk_gmd_blender'
    spec = importlib.util.spec_from_file_location('yk_gmd_blender', package/'__init__.py', submodule_search_locations=[str(package)])
    mod = importlib.util.module_from_spec(spec); sys.modules['yk_gmd_blender'] = mod
    spec.loader.exec_module(mod); mod.register()


def inspect(path):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    status = bpy.ops.import_scene.gmd_skinned(filepath=str(path), strict=True, stop_on_fail=True,
        import_materials=True, import_hierarchy=True, import_objects=True)
    if status != {'FINISHED'}: raise RuntimeError('GMD importer status: '+repr(status))
    rigs = sorted((o for o in bpy.data.objects if o.type=='ARMATURE'), key=lambda o:len(o.data.bones), reverse=True)
    rig = rigs[0] if rigs else None
    bones = list(rig.data.bones) if rig else []
    parent_sig = sorted((b.name, b.parent.name if b.parent else None) for b in bones)
    rest = sorted((b.name, b.parent.name if b.parent else '',
                   tuple(round(float(v),7) for row in b.matrix_local for v in row)) for b in bones)
    meshes=[]; shaders=[]
    for ob in (o for o in bpy.data.objects if o.type=='MESH'):
        mats=[]
        for m in ob.data.materials:
            if not m: continue
            shader = m.yakuza_data.shader_name if m.yakuza_data.inited else None
            node = next((n for n in m.node_tree.nodes if n.type == 'GROUP'
                         and n.node_tree and n.node_tree.name == 'YakuzaShaderNode'), None) if m.node_tree else None
            props = {}
            if node:
                for key in ('Opacity', 'Specular color'):
                    socket = node.inputs.get(key)
                    if socket:
                        value = socket.default_value
                        props[key] = float(value) if isinstance(value, (int,float)) else list(value)
            mats.append({'name':m.name,'shader':str(shader) if shader is not None else None,'properties':props})
            if shader is not None: shaders.append(str(shader))
        meshes.append({'name':ob.name,'vertices':len(ob.data.vertices),'faces':len(ob.data.polygons),'materials':mats})
    return {'load_status':'loaded','scene_name':rig.name if rig else None,'rig_name':rig.name if rig else None,
      'bone_count':len(bones),'bone_names':sorted(b.name for b in bones),'parent_signature':parent_sig,
      'rest_transforms':rest,'meshes':meshes,'mesh_count':len(meshes),'shaders':sorted(set(shaders)),'warnings':[]}

if __name__=='__main__':
    arg=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf8'))
    load_addon(arg['addon']); out=[]
    for item in arg['files']:
        try: result=inspect(item['absolute_path'])
        except Exception as e: result={'load_status':'failed','error':str(e),'warnings':[traceback.format_exc(limit=2)]}
        out.append({'absolute_path':item['absolute_path'],**result})
    Path(arg['output']).write_text(json.dumps(out,ensure_ascii=False),encoding='utf8')
