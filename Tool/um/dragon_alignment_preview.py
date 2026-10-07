"""Create an explicitly separate, unexportable spatial alignment preview in Blender.

Run with existing offline workspace.blend and -- alignment.json NEW_preview.blend [source.vrm].
Only duplicates of VRM rig/skinned meshes are transformed. Original objects, GMDs and game install are not changed.

With the source VRM given, the vertices are placed where the glTF specification puts them (see dragon_vrm_skin.py)
instead of where Blender's importer left them, and meshes that have their own skeleton or none (a twintail added on
its own bones, a hairpin, a prop on a bone) are attached to the main rig through the nearest ancestor bone.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


RIGID_RESIDUAL_M = 0.01


def affine_residual(before, after) -> float:
    """Largest distance between `after` and the best affine transform of `before` (flat xyz lists)."""
    import numpy as np
    x = np.asarray(before, dtype=float).reshape(-1, 3)
    y = np.asarray(after, dtype=float).reshape(-1, 3)
    design = np.hstack([x, np.ones((len(x), 1))])
    solution, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(np.linalg.norm(design @ solution - y, axis=1).max())


def bake_pose_into_meshes(rig, objects):
    """Fallback without the VRM file: bake the armature's current pose into the vertices, only when the pose moves
    the whole mesh like one transform (move/rotate/scale); a mesh the pose would distort keeps its vertices."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    moved = {}
    skipped = {}
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if len(mesh.vertices) != len(obj.data.vertices):
                continue
            count = len(obj.data.vertices)
            posed = [0.0] * (count * 3)
            mesh.vertices.foreach_get('co', posed)
            raw = [0.0] * (count * 3)
            obj.data.vertices.foreach_get('co', raw)
        finally:
            evaluated.to_mesh_clear()
        delta = [p - r for p, r in zip(posed, raw)]
        if max((abs(d) for d in delta), default=0.0) < 1e-6:
            continue
        residual = affine_residual(raw, posed)
        if residual > RIGID_RESIDUAL_M:
            skipped[obj.name] = round(residual, 4)
            continue
        obj.data.vertices.foreach_set('co', posed)
        if obj.data.shape_keys:
            for block in obj.data.shape_keys.key_blocks:
                coords = [0.0] * (count * 3)
                block.data.foreach_get('co', coords)
                block.data.foreach_set('co', [c + d for c, d in zip(coords, delta)])
        obj.data.update()
        moved[obj.name] = round(max(abs(d) for d in delta), 4)
    if skipped:
        print('DRAGON_POSE_NOT_BAKED', skipped)
    return moved


def reset_pose(rig):
    for bone in rig.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


def read_vrm(vrm_path):
    """VrmSkin of the source VRM, or None when it cannot be read (the Blender pose is used then)."""
    if not vrm_path:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from dragon_vrm_skin import VrmSkin
        return VrmSkin(vrm_path)
    except Exception as exc:  # noqa: BLE001 - never stop the conversion because of the extra data
        print('DRAGON_VRM_SKIN_UNAVAILABLE', exc)
        return None


def lookup_node(skin_nodes, object_name):
    """glTF mesh node for a Blender object; Blender adds .001 to duplicate names."""
    if object_name in skin_nodes:
        return skin_nodes[object_name]
    if len(object_name) > 4 and object_name[-4] == '.' and object_name[-3:].isdigit():
        return skin_nodes.get(object_name[:-4])
    return None


def set_vertices(obj, world_points, transform):
    """Place the mesh so that obj.matrix_world @ vertex == transform @ world_points (Blender world space)."""
    import numpy as np
    inverse = np.array(obj.matrix_world.inverted() @ transform)
    homogeneous = np.hstack([world_points, np.ones((len(world_points), 1))])
    local = (inverse @ homogeneous.T).T[:, :3].reshape(-1)
    count = len(obj.data.vertices)
    old = np.zeros(count * 3)
    obj.data.vertices.foreach_get('co', old)
    delta = local - old
    obj.data.vertices.foreach_set('co', local)
    if obj.data.shape_keys:  # the shape keys keep their shape relative to the new base
        for block in obj.data.shape_keys.key_blocks:
            coords = np.zeros(count * 3)
            block.data.foreach_get('co', coords)
            block.data.foreach_set('co', coords + delta)
    obj.data.update()


def rebuild_weights(obj, skin, node_index, main_bones, joint_nodes, weights):
    """Weights on the main rig for a mesh that has its own skeleton (or none): every joint becomes the nearest
    ancestor bone that exists in the main rig (a twintail on its own bones follows the head, for example)."""
    fallback = skin.ancestor_in(node_index, main_bones)
    if fallback is None:
        raise RuntimeError(f'{obj.name} is not attached to the avatar skeleton')
    obj.vertex_groups.clear()
    groups = {}
    names_of = {}
    for vertex in range(len(obj.data.vertices)):
        merged = {}
        if joint_nodes is None:
            merged[fallback] = 1.0
        else:
            for k in range(4):
                weight = float(weights[vertex][k])
                if weight <= 0:
                    continue
                joint = int(joint_nodes[vertex][k])
                if joint not in names_of:
                    names_of[joint] = skin.ancestor_in(joint, main_bones) or fallback
                merged[names_of[joint]] = merged.get(names_of[joint], 0.0) + weight
        total = sum(merged.values())
        if total <= 0:
            merged, total = {fallback: 1.0}, 1.0
        for name, weight in merged.items():
            if name not in groups:
                groups[name] = obj.vertex_groups.new(name=name)
            groups[name].add([vertex], weight / total, 'REPLACE')
    return sorted(groups)


def run(audit, dest, vrm_path=None):
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
    skin = read_vrm(vrm_path)
    skin_nodes = {}
    if skin:
        for index in skin.mesh_nodes():
            skin_nodes.setdefault(skin.name(index), index)
    main_bones = {bone.name for bone in rig.data.bones}
    chosen = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        on_main_rig = obj.find_armature() == rig and obj.parent == rig
        node = lookup_node(skin_nodes, obj.name) if skin else None
        positions = None
        if node is not None:
            try:
                positions = skin.final_positions(node)
            except Exception as exc:  # noqa: BLE001
                print('DRAGON_VRM_SKIN_FAILED', obj.name, exc)
            if positions is not None and len(positions[0]) != len(obj.data.vertices):
                positions = None  # Blender merged or split vertices: cannot map them one to one
        if on_main_rig or positions is not None:
            chosen.append((obj, node, positions))
    if not chosen:
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
    previews = []
    for source, node, positions in chosen:
        obj = source.copy()
        obj.data = source.data.copy()  # original shape keys and mesh stay untouched
        obj.name = 'PREVIEW_ONLY_' + source.name
        collection.objects.link(obj)
        obj.parent = copied
        obj.animation_data_clear()
        if positions is not None:
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_world = copied.matrix_world  # same scale as the rig; the vertices carry the exact placement
        else:
            obj.matrix_parent_inverse = source.matrix_parent_inverse.copy()
            obj.matrix_world = transform @ source.matrix_world
        armature_modifiers = [m for m in obj.modifiers if m.type == 'ARMATURE']
        if armature_modifiers:
            for modifier in armature_modifiers:
                modifier.object = copied
        else:
            obj.modifiers.new('Armature', 'ARMATURE').object = copied
        previews.append((obj, source, node, positions))
    bpy.context.view_layer.update()
    report = {'from_vrm_file': [], 'blender_pose': [], 'moved_to_main_rig': [], 'left_out': []}
    fallback_objects = []
    for obj, source, node, positions in previews:
        if positions is None:
            fallback_objects.append(obj)
            continue
        from dragon_vrm_skin import gltf_to_blender
        set_vertices(obj, gltf_to_blender(positions[0]), transform)
        report['from_vrm_file'].append(source.name)
        if source.find_armature() != rig:
            rebuild_weights(obj, skin, node, main_bones, positions[1], positions[2])
            report['moved_to_main_rig'].append(source.name)
    if fallback_objects:
        report['blender_pose'] = [o.name for o in fallback_objects]
        bake_pose_into_meshes(copied, fallback_objects)
    reset_pose(copied)
    for obj, source, node, positions in previews:
        if obj.find_armature() != copied:
            raise RuntimeError(f'Preview armature mismatch: {source.name}')
    included = {src.name for _, src, _, _ in previews}
    if skin:
        report['left_out'] = [o.name for o in bpy.data.objects if o.type == 'MESH'
                              and lookup_node(skin_nodes, o.name) is not None and o.name not in included]
    copied['DRAGON_PREVIEW_UNVERIFIED'] = 'spatial only; no retarget, GMD export or pose tests'
    bpy.context.scene['DRAGON_PREVIEW_UNVERIFIED'] = 'do not export or install'
    bpy.ops.wm.save_as_mainfile(filepath=str(dest), check_existing=False)
    dest.with_suffix('.meshes.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('DRAGON_PREVIEW_MESHES', {k: len(v) for k, v in report.items()})
    print('DRAGON_SPATIAL_PREVIEW_OK', len(previews), dest)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) not in (2, 3):
        raise SystemExit('expected -- alignment.json NEW_preview.blend [source.vrm]')
    run(json.loads(Path(args[0]).read_text(encoding='utf-8')), Path(args[1]), args[2] if len(args) == 3 else None)
