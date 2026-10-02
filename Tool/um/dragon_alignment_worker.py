"""Blender-only read-only alignment audit for an imported VRM/GMD workspace.

Usage: blender --background workspace.blend --python this_script -- mapping.json output.json
No meshes, rigs, source files or .blend workspaces are written.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


TARGET = {
    "hips": "ketu_c_n", "head": "face_c_n", "leftShoulder": "kata_l_n",
    "rightShoulder": "kata_r_n", "leftUpperArm": "ude1_l_n", "rightUpperArm": "ude1_r_n",
    "leftHand": "ude3_l_n", "rightHand": "ude3_r_n",
    "leftFoot": "asi3_l_n", "rightFoot": "asi3_r_n",
}


def find_rig(prefix, required):
    candidates = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE'
                  and (obj.name.startswith(prefix) if prefix else not obj.name.startswith('c_cl_'))
                  and all(n in obj.data.bones for n in required)]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one rig for {prefix}, found {[o.name for o in candidates]}")
    return candidates[0]


def world_head(rig, name):
    return rig.matrix_world @ rig.data.bones[name].head_local


def basis(hip, head, left_shoulder, right_shoulder):
    up = (head - hip).normalized()
    across = right_shoulder - left_shoulder
    across -= up * across.dot(up)
    right = across.normalized()
    forward = up.cross(right).normalized()
    if min(up.length, right.length, forward.length) < .99:
        raise RuntimeError("Degenerate humanoid pose")
    return Matrix((right, forward, up)).transposed()


def audit(mapping):
    source_names = {entry['role']: entry['source_bone'] for entry in mapping['fit_plan']['matched_roles']}
    missing = [role for role in TARGET if role not in source_names]
    if missing:
        raise RuntimeError(f"Missing source roles for alignment: {missing}")
    source = find_rig('', [source_names[r] for r in TARGET])
    target_prefix = mapping.get("target_rig_prefix")
    if not target_prefix:
        raise RuntimeError(f"Missing target rig prefix for {mapping.get('target_id', 'yagami')}")
    target = find_rig(target_prefix, list(TARGET.values()))
    s = {role: world_head(source, source_names[role]) for role in TARGET}
    t = {role: world_head(target, target_bone) for role, target_bone in TARGET.items()}
    sh = (s['head'] - s['hips']).length
    th = (t['head'] - t['hips']).length
    # Clavicle-root bones sit near the centre in this GMD; upper-arm joints
    # describe the shoulder span much more reliably than the kata bone heads.
    sw = (s['rightUpperArm'] - s['leftUpperArm']).length
    tw = (t['rightUpperArm'] - t['leftUpperArm']).length
    if min(sh, th, sw, tw) < .01:
        raise RuntimeError("Degenerate avatar or target height/shoulder width")
    source_basis = basis(s['hips'], s['head'], s['leftUpperArm'], s['rightUpperArm'])
    target_basis = basis(t['hips'], t['head'], t['leftUpperArm'], t['rightUpperArm'])
    rotation = target_basis @ source_basis.transposed()
    scale = th / sh
    translation = t['hips'] - scale * (rotation @ s['hips'])
    residuals = {role: round(100 * ((translation + scale * (rotation @ point)) - t[role]).length, 3)
                 for role, point in s.items()}
    return {
        'source_rig': source.name, 'target_rig': target.name,
        'height_m': {'vrm': round(sh, 5), 'target': round(th, 5)},
        'upper_arm_joint_width_m': {'vrm': round(sw, 5), 'target': round(tw, 5)},
        'uniform_scale': round(scale, 6), 'upper_arm_width_ratio_after_scale': round(scale * sw / tw, 4),
        'rotation_rows': [[round(v, 8) for v in row] for row in rotation],
        'translation_m': [round(v, 6) for v in translation],
        'rest_residual_cm': residuals,
        'geometry_changed': False, 'weights_changed': False, 'workspace_saved': False,
        'note': 'Anatomical landmark proposal only; bind poses and animations NOT tested',
    }


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) != 2:
        raise SystemExit('expected -- mapping.json result.json')
    mapping = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    result = audit(mapping)
    Path(args[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('DRAGON_ALIGNMENT_AUDIT_OK')
