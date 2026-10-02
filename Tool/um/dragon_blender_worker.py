"""Ephemeral Blender worker. Run only via Blender --background --factory-startup.

Uses the user's local GMD addon source without installing or registering it in preferences.
No game files are written. An optional new .blend is saved only to the requested
private workspace path; the inspection JSON goes to a temporary host path.
"""
import importlib.util
import json
import sys
from pathlib import Path

import bpy


def _load_gmd_addon(folder):
    package = folder / "yk_gmd_blender"
    init = package / "__init__.py"
    if not init.is_file():
        raise RuntimeError("Expected yk_gmd_blender/__init__.py inside addon folder")
    spec = importlib.util.spec_from_file_location("yk_gmd_blender", init,
                                                   submodule_search_locations=[str(package)])
    addon = importlib.util.module_from_spec(spec)
    sys.modules["yk_gmd_blender"] = addon
    spec.loader.exec_module(addon)
    addon.register()  # in this factory-startup process only; never save preferences


def _snapshot(rig):
    return {'rig_world':[float(v) for row in rig.matrix_world for v in row],
            'bones':[{'name':b.name,'parent':b.parent.name if b.parent else None,
                      'matrix':[float(v) for row in b.matrix_local for v in row],
                      'head':[float(v) for v in b.head_local],
                      'tail':[float(v) for v in b.tail_local]}
                     for b in sorted(rig.data.bones,key=lambda b:b.name)]}


def _stats(objects, measure_skeleton=False):
    meshes = [o for o in objects if o.type == "MESH"]
    rigs = [o for o in objects if o.type == "ARMATURE"]
    return {
        "mesh_count": len(meshes), "armature_count": len(rigs),
        "bone_counts": [len(r.data.bones) for r in rigs],
        "rig_names": [r.name for r in rigs],
        "skeletons": [_snapshot(r) for r in rigs] if measure_skeleton else [],
        "vertices": sum(len(m.data.vertices) for m in meshes),
        "faces": sum(len(m.data.polygons) for m in meshes),
        "material_slots": sum(len(m.material_slots) for m in meshes),
        "meshes_without_uv": [m.name for m in meshes if not m.data.uv_layers],
        "meshes_without_armature": [m.name for m in meshes if not m.find_armature()],
    }


def run(job):
    _load_gmd_addon(Path(job["addon"]))
    references = {}
    imported = {}
    target_bones = []
    for role, path in job["references"].items():
        key = str(Path(path).resolve())
        if key not in imported:
            before = set(bpy.data.objects)
            status = bpy.ops.import_scene.gmd_skinned(
                filepath=path, strict=True, stop_on_fail=True,
                import_materials=True, import_hierarchy=True, import_objects=True,
            )
            if status != {'FINISHED'}:
                raise RuntimeError(f"Strict GMD import failed: {role}: {status}")
            added = set(bpy.data.objects) - before
            stats = _stats(added, measure_skeleton=True)
            if not stats["mesh_count"] or not stats["armature_count"]:
                raise RuntimeError(f"GMD import has no mesh or skeleton: {role}")
            imported[key] = (added, stats)
        added, references[role] = imported[key]
        if role == "tops":
            rig = max((o for o in added if o.type == "ARMATURE"), key=lambda o: len(o.data.bones))
            target_bones = [bone.name for bone in rig.data.bones]
    before = set(bpy.data.objects)
    status = bpy.ops.import_scene.gltf(filepath=job["vrm"])
    if status != {'FINISHED'}:
        raise RuntimeError(f"Blender glTF import failed: {status}")
    source_objects = set(bpy.data.objects) - before
    avatar = _stats(source_objects)
    if not avatar["mesh_count"] or not avatar["armature_count"]:
        raise RuntimeError("VRM import has no mesh or skeleton")
    result = {"blender_version": bpy.app.version_string, "gmd_addon": "local yk_gmd_blender",
              "target_id": job.get("target_id", "yagami"),
              "strict_gmd_import": True, "vrm": avatar, "references": references,
              "export_verified": False, "motion_verified": False,
              "build_ready": False, "installed": False}
    if job.get("workspace"):
        rig = max((o for o in source_objects if o.type == "ARMATURE"),
                  key=lambda o: len(o.data.bones))
        groups = sorted({group.name for obj in source_objects if obj.type == "MESH"
                         for group in obj.vertex_groups})
        result["fit_inputs"] = {"vrm_bones": [b.name for b in rig.data.bones],
                                "vertex_groups": groups, "target_bones": target_bones}
        output = Path(job["workspace"])
        if output.exists() or not output.parent.is_dir() or output.suffix.lower() != ".blend":
            raise RuntimeError("Workspace must be a new .blend file in an existing directory")
        bpy.context.scene["DRAGON_WORKSPACE_NOT_EXPORTED"] = "Imported references only; no retarget or GMD export"
        bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
        result["workspace"] = str(output)
    return result


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1:]
    if len(arguments) != 2:
        raise SystemExit("expected -- job.json result.json")
    job = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    report = run(job)
    Path(arguments[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DRAGON_BLENDER_INSPECT_OK")
