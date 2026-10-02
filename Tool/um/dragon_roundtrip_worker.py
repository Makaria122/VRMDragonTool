"""Strict roundtrip of a target GMD in an isolated Blender process.

Inputs: -- job.json result.json. Target is an existing private copy, NEVER the
original extracted GMD or game install. No avatar conversion is performed.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import kdtree


def load_addon(folder):
    package = folder / 'yk_gmd_blender'
    spec = importlib.util.spec_from_file_location('yk_gmd_blender', package / '__init__.py',
                                                   submodule_search_locations=[str(package)])
    addon = importlib.util.module_from_spec(spec)
    sys.modules['yk_gmd_blender'] = addon
    spec.loader.exec_module(addon)
    addon.register()


def stats(objects):
    rigs = [o for o in objects if o.type == 'ARMATURE']
    meshes = [o for o in objects if o.type == 'MESH']
    return {'rigs': len(rigs), 'bones': [len(r.data.bones) for r in rigs],
            'meshes': len(meshes), 'vertices': sum(len(o.data.vertices) for o in meshes),
            'faces': sum(len(o.data.polygons) for o in meshes),
            'uvless': [o.name for o in meshes if not o.data.uv_layers],
            'nonfinite_vertices': sum(not all(math.isfinite(c) for c in v.co)
                                      for o in meshes for v in o.data.vertices)}


def closest_error(left, right):
    if not left or not right:
        raise RuntimeError('No geometry to compare')
    tree = kdtree.KDTree(len(right))
    for index, point in enumerate(right):
        tree.insert(point, index)
    tree.balance()
    return max(tree.find(point)[2] for point in left)


def geometry_points(objects):
    return [o.matrix_world @ v.co for o in objects if o.type == 'MESH' for v in o.data.vertices]


def bone_heads(objects):
    rig = next(o for o in objects if o.type == 'ARMATURE')
    return {bone.name: rig.matrix_world @ bone.head_local for bone in rig.data.bones}


def run(job):
    source = Path(job['source']).resolve(strict=True)
    target = Path(job['target']).resolve(strict=True)
    if source == target or source.read_bytes() != target.read_bytes():
        raise RuntimeError('Output must be a byte-identical private target copy, never source')
    load_addon(Path(job['addon']))
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    if bpy.ops.import_scene.gmd_skinned(filepath=str(source), strict=True,
                                         import_materials=True, import_hierarchy=True,
                                         import_objects=True) != {'FINISHED'}:
        raise RuntimeError('Source strict import failed')
    source_objects = list(bpy.context.scene.objects)
    original = stats(source_objects)
    expected_bones=job.get('expected_bone_count',358)
    if original['rigs'] != 1 or original['bones'] != [expected_bones] or not original['meshes']:
        raise RuntimeError(f'Expected one {expected_bones}-bone skinned character: {original}')
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    exported = bpy.ops.export_scene.gmd_skinned(filepath=str(target),
                                                  bone_matrix_origin='FROM_TARGET_FILE', strict=True)
    if exported != {'FINISHED'}:
        raise RuntimeError(f'Strict export failed: {exported}')
    verify_scene = bpy.data.scenes.new('DragonRoundtripVerification')
    bpy.context.window.scene = verify_scene
    before = set(bpy.data.objects)
    if bpy.ops.import_scene.gmd_skinned(filepath=str(target), strict=True,
                                         import_materials=True, import_hierarchy=True,
                                         import_objects=True) != {'FINISHED'}:
        raise RuntimeError('Exported copy strict reimport failed')
    verified_objects = set(bpy.data.objects) - before
    verified = stats(verified_objects)
    if any(original[key] != verified[key] for key in ('rigs', 'bones', 'meshes', 'faces', 'uvless', 'nonfinite_vertices')):
        raise RuntimeError(f'Roundtrip structural totals changed: {original} -> {verified}')
    left, right = geometry_points(source_objects), geometry_points(verified_objects)
    max_deviation = max(closest_error(left, right), closest_error(right, left))
    if max_deviation > 2e-5:
        raise RuntimeError(f'Roundtrip geometry changed by {max_deviation:.7f}m')
    bone_a, bone_b = bone_heads(source_objects), bone_heads(verified_objects)
    if bone_a.keys() != bone_b.keys():
        raise RuntimeError('Target skeleton bone names changed')
    max_bone_delta = max((bone_a[name]-bone_b[name]).length for name in bone_a)
    if max_bone_delta > 2e-5:
        raise RuntimeError(f'Target rest bones changed by {max_bone_delta:.7f}m')
    return {'source': str(source), 'working_copy': str(target), 'original': original,
            'verified': verified, 'max_coordinate_delta_m': max_deviation,
            'max_bone_head_delta_m': max_bone_delta,
            'vertex_split_delta': verified['vertices'] - original['vertices'],
            'strict_roundtrip': True,
            'avatar_converted': False, 'game_install_changed': False}


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) != 2:
        raise SystemExit('expected -- job.json result.json')
    job = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    result = run(job)
    Path(args[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
    print('DRAGON_STRICT_GMD_ROUNDTRIP_OK')
