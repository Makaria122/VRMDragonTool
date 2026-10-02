"""Read-only structural audit of a private, experimental full GMD region.

Requires the same JSON job used by dragon_full_draft_worker. It cannot certify
animated quality or game appearance. Creates only a new JSON audit report.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector, kdtree

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dragon_geometry_fit import bounded_offsets, weighted_bone_offsets
from dragon_anatomical_fit import fit_points


def addon(folder):
    package=folder/'yk_gmd_blender'
    spec=importlib.util.spec_from_file_location('yk_gmd_blender',package/'__init__.py',
                                                submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec)
    sys.modules['yk_gmd_blender']=module
    spec.loader.exec_module(module)
    module.register()


def max_near(a,b):
    if not a or not b:raise RuntimeError('Cannot compare empty mesh')
    tree=kdtree.KDTree(len(b))
    for i,v in enumerate(b):tree.insert(v,i)
    tree.balance()
    return max(tree.find(v)[2] for v in a)


def library_world(obj):
    if obj.parent is None:
        return obj.matrix_basis.copy()
    if obj.parent_type != 'OBJECT':
        raise RuntimeError(f'Unsupported bone-parented source: {obj.name}')
    return library_world(obj.parent) @ obj.matrix_parent_inverse @ obj.matrix_basis


def audit(job):
    addon(Path(job['addon']))
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    if bpy.ops.import_scene.gmd_skinned(filepath=job['working_copy'],strict=True,
                                         import_materials=True,import_hierarchy=True,
                                         import_objects=True)!={'FINISHED'}:
        raise RuntimeError('Draft GMD strict import failed')
    scene=bpy.context.scene
    meshes=[o for o in scene.objects if o.type=='MESH']
    rig=next(o for o in scene.objects if o.type=='ARMATURE')
    expected_bones=job.get('target_bone_count',358)
    if len(meshes)!=len(job['meshes']) or len(rig.data.bones)!=expected_bones:
        raise RuntimeError('Draft mesh or skeleton count changed')
    region=job['region']
    audit=[]
    for index, entry in enumerate(job['meshes']):
        name=f'[l0]vrm_{region}_{index:02}'
        matches=[o for o in meshes if o.name==name]
        if len(matches)!=1:raise RuntimeError(f'GMD draft mesh missing: {name}')
        actual=matches[0]
        with bpy.data.libraries.load(entry['blend'],link=False) as (src,dst):
            if entry['object'] not in src.objects:raise RuntimeError('Missing private source mesh')
            dst.objects=[entry['object']]
        original=dst.objects[0]
        world=library_world(original)
        a=[world @ v.co for v in original.data.vertices]
        if str(index) in job.get('mesh_offsets',{}):
            files=job['mesh_offsets'][str(index)]
            source_data=json.loads(Path(files['source_data']).read_text(encoding='utf-8'))
            fit=json.loads(Path(files['solver_result']).read_text(encoding='utf-8'))
            if (fit.get('source_mesh')!=original.name or fit.get('game_install_authorized') is not False
                    or len(source_data['vertices'])!=len(a) or len(fit['offsets'])!=len(a)):
                raise RuntimeError('Solver source data does not match the audit mesh')
            for i,raw in enumerate(source_data['vertices']):
                if (a[i]-type(a[i])(raw)).length>2e-5:
                    raise RuntimeError('Stale solver input geometry')
            a=[point+type(point)(fit['offsets'][i]) for i,point in enumerate(a)]
        if job.get('anatomical_fit'):
            names=[g.name for g in original.vertex_groups]
            weights=[{names[w.group]:w.weight for w in v.groups} for v in original.data.vertices]
            a=[Vector(p) for p in fit_points([list(p) for p in a],weights,job['anatomical_fit'])]
        foot_targets=job.get('foot_fit_targets',[])
        if foot_targets:
            source_map={x['source_bone']:x['target_bone'] for x in job['matched_roles']}
            source_map.update({x['source_group']:x['suggested_target'] for x in job.get('accessory_parent_hints',[])})
            group_names=[g.name for g in original.vertex_groups]
            group_rows=[[(w.group,w.weight) for w in vertex.groups] for vertex in original.data.vertices]
            offsets=weighted_bone_offsets(group_rows,group_names,source_map,
                                          job['foot_joint_deltas'],foot_targets)
            alpha,corrected=bounded_offsets([tuple(point) for point in a],
                [tuple(edge.vertices) for edge in original.data.edges],offsets,max_stretch=1.5)
            a=[Vector(point) for point in corrected]
        b=[actual.matrix_world @ v.co for v in actual.data.vertices]
        distance=max(max_near(a,b),max_near(b,a))
        if distance>2e-5:
            raise RuntimeError(f'Geometry coordinate mismatch in {name}: max delta {distance}m')
        source_faces=len(original.data.polygons)
        gmd_faces=len(actual.data.polygons)
        face_delta=gmd_faces-source_faces
        # Exporters may discard degenerate/duplicate triangles on roundtrip.
        # Preserve and report topology changes instead of treating every VRM as
        # a failed conversion when its coordinates and strict GMD import pass.
        topology_warning=(f'face count changed {source_faces}->{gmd_faces}'
                          if face_delta else None)
        if not actual.data.uv_layers or not actual.material_slots:
            raise RuntimeError(f'Missing UV or material in {name}')
        if any(not v.groups or len(v.groups)>4 or not all(math.isfinite(c) for c in v.co)
               for v in actual.data.vertices):
            raise RuntimeError(f'Unweighted/nonfinite/too many influences: {name}')
        audit.append({'name':name,'source_vertices':len(a),'gmd_vertices':len(b),
                      'source_faces':source_faces,'gmd_faces':gmd_faces,
                      'face_delta':face_delta,'topology_warning':topology_warning,
                      'max_position_delta_m':distance,'materials':len(actual.material_slots)})
    payload=Path(job['working_copy']).read_bytes()
    material_manifest=json.loads(Path(job['texture_map']).read_text(encoding='utf-8'))
    referenced=sorted({Path(m['dds']).stem for m in material_manifest['materials'] if m.get('dds')
                       and Path(job['dds_dir'],m['dds']).is_file() and Path(m['dds']).stem.encode('ascii') in payload})
    if not referenced:raise RuntimeError('No private DDS texture names found in exported GMD')
    return {'region':region,'strict_gmd_import':True,'target_bones':expected_bones,'meshes':audit,
            'solver_offsets_audited':bool(job.get('mesh_offsets')),
            'dds_stems_found':referenced,'rest_geometry_verified':True,
            'topology_warnings':[m['topology_warning'] for m in audit if m['topology_warning']],
            'skin_pose_verified':False,'shader_appearance_verified':False,
            'ready_for_game':False,'game_install_changed':False}


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=2:raise SystemExit('expected -- job.json NEW_report.json')
    report=audit(json.loads(Path(args[0]).read_text(encoding='utf-8')))
    with Path(args[1]).open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write('\n')
    print('DRAGON_FULL_DRAFT_AUDIT_OK',report['region'])
