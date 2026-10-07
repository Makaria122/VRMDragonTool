"""Create an explicitly separate, unexportable spatial alignment preview in Blender.

Run with existing offline workspace.blend and -- alignment.json NEW_preview.blend.
Only duplicates of VRM rig/skinned meshes are transformed. No weights are remapped;
original objects, GMDs and game install are not changed.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def bake_pose_into_meshes(rig, objects):
    """Bake the armature's current pose into the vertices and return to the rest pose.

    Avatars exported from Unity can carry bones whose pose differs from the bind pose the skin was written with
    (hair added with its own armature, props placed on bones, hand-adjusted bones). Viewers and Unity show the
    posed shape, so the posed shape is the intended one; reading the raw vertices instead put such meshes in
    the wrong place (a twintail two metres away, a hairpin at the feet). Meshes whose pose equals the bind pose
    do not change.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    moved = {}
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if len(mesh.vertices) != len(obj.data.vertices):
                continue  # other modifiers change the vertex count; leave the mesh as it is
            count = len(obj.data.vertices)
            posed = [0.0] * (count * 3)
            mesh.vertices.foreach_get('co', posed)
            raw = [0.0] * (count * 3)
            obj.data.vertices.foreach_get('co', raw)
        finally:
            evaluated.to_mesh_clear()
        delta = [p - r for p, r in zip(posed, raw)]
        biggest = max((abs(d) for d in delta), default=0.0)
        if biggest < 1e-6:
            continue
        obj.data.vertices.foreach_set('co', posed)
        if obj.data.shape_keys:  # keep the shape keys relative to the new base shape
            for block in obj.data.shape_keys.key_blocks:
                coords = [0.0] * (count * 3)
                block.data.foreach_get('co', coords)
                block.data.foreach_set('co', [c + d for c, d in zip(coords, delta)])
        obj.data.update()
        moved[obj.name] = round(biggest, 4)
    for bone in rig.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    return moved


def run(audit, dest):
    if dest.exists() or dest.suffix.lower() != '.blend' or not dest.parent.is_dir():
        raise RuntimeError('Choose a NEW .blend in an existing private folder')
    if audit.get('geometry_changed') or audit.get('weights_changed'):
        raise RuntimeError('Expected a read-only alignment audit')
    scale = audit['uniform_scale']
    if not .3 < scale < 3:
        raise RuntimeError('Refusing extreme preview scale')
    rig = bpy.data.objects[audit['source_rig']]
    if rig.type != 'ARMATURE':
        raise RuntimeError('Source rig missing')
    target = bpy.data.objects[audit['target_rig']]
    if target.type != 'ARMATURE':
        raise RuntimeError('Target reference rig missing')
    meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH'
              and obj.find_armature() == rig and obj.parent == rig]
    if not meshes:
        raise RuntimeError('No source skinned meshes to preview')
    rotation = Matrix(audit['rotation_rows']).to_4x4()
    translation = Matrix.Translation(Vector(audit['translation_m']))
    transform = translation @ rotation @ Matrix.Scale(scale, 4)
    collection = bpy.data.collections.new('DRAGON_ALIGNMENT_PREVIEW_NOT_EXPORTED')
    bpy.context.scene.collection.children.link(collection)
    copied = rig.copy()
    copied.data = rig.data.copy()
    copied.name = 'PREVIEW_ONLY_' + rig.name
    collection.objects.link(copied)
    copied.parent = None
    copied.matrix_world = transform @ rig.matrix_world
    copied.animation_data_clear()
    for source in meshes:
        obj = source.copy()
        obj.data = source.data.copy()  # original shape keys and mesh stay untouched
        obj.name = 'PREVIEW_ONLY_' + source.name
        collection.objects.link(obj)
        obj.parent = copied
        obj.matrix_parent_inverse = source.matrix_parent_inverse.copy()
        obj.matrix_world = transform @ source.matrix_world
        obj.animation_data_clear()
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object == rig:
                modifier.object = copied
        if obj.find_armature() != copied:
            raise RuntimeError(f'Preview armature mismatch: {source.name}')
    bpy.context.view_layer.update()
    baked = bake_pose_into_meshes(copied, [o for o in collection.objects if o.type == 'MESH'])
    copied['DRAGON_PREVIEW_UNVERIFIED'] = 'spatial only; no retarget, GMD export or pose tests'
    bpy.context.scene['DRAGON_PREVIEW_UNVERIFIED'] = 'do not export or install'
    bpy.ops.wm.save_as_mainfile(filepath=str(dest), check_existing=False)
    print('DRAGON_POSE_BAKED', baked)
    print('DRAGON_SPATIAL_PREVIEW_OK', len(meshes), dest)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) != 2:
        raise SystemExit('expected -- alignment.json NEW_preview.blend')
    run(json.loads(Path(args[0]).read_text(encoding='utf-8')), Path(args[1]))
