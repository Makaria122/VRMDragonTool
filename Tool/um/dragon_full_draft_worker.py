"""EXPERIMENTAL private full-avatar GMD draft, NEVER game-ready automatically.

One Blender process/region: -- job.json result.json. Stages mapped VRM meshes on
unchanged original target armature, assigns local DDS to cloned target shaders,
exports ONLY a preexisting private copied GMD and strict-reimports it. Collapsing
non-humanoid weights to parent is visibly lossy; result always requires review.
"""
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dragon_geometry_fit import bounded_offsets, limiting_edge, weighted_bone_offsets
from dragon_anatomical_fit import fit_points
from dragon_material_maps import (apply_dummy_maps, verify_dummy_references,
                                  select_material_template, apply_matte_specular)


def addon(folder):
    package=folder/'yk_gmd_blender'
    spec=importlib.util.spec_from_file_location('yk_gmd_blender',package/'__init__.py',
                                                submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec)
    sys.modules['yk_gmd_blender']=module
    spec.loader.exec_module(module)
    module.register()


def library_world(obj):
    """Library-loaded objects are unlinked: matrix_world is stale identity until evaluated."""
    if obj.parent is None:
        return obj.matrix_basis.copy()
    if obj.parent_type != 'OBJECT':
        raise RuntimeError(f'Unsupported bone-parented source: {obj.name}')
    return library_world(obj.parent) @ obj.matrix_parent_inverse @ obj.matrix_basis


def run(job):
    original=Path(job['original_gmd']).resolve(strict=True)
    working=Path(job['working_copy']).resolve(strict=True)
    expected_scale=job.get('expected_source_scale')
    if type(expected_scale) not in (int,float) or not math.isfinite(expected_scale) or expected_scale<=0:
        raise RuntimeError('Explicit positive expected_source_scale is required')
    if original==working or original.read_bytes()!=working.read_bytes():
        raise RuntimeError('Working GMD must be an untouched PRIVATE copy')
    source_map={x['source_bone']:x['target_bone'] for x in job['matched_roles']}
    accessory={x['source_group']:x['suggested_target'] for x in job['accessory_parent_hints']}
    overlap=set(source_map)&set(accessory)
    if overlap:
        raise RuntimeError(f'Ambiguous source mappings: {sorted(overlap)}')
    source_map.update(accessory)
    rest_fit=job.get('rest_fit_report')
    bone_deltas={}
    if rest_fit:
        proposal=json.loads(Path(rest_fit).read_text(encoding='utf-8'))
        for row in proposal['joints']:
            source_name,target_name=row['source'],row['target']
            if source_map.get(source_name)!=target_name:
                raise RuntimeError(f'Rest-fit mapping mismatch: {source_name}')
            delta=row['world_delta_m']
            if len(delta)!=3 or not all(type(c) in (int,float) and math.isfinite(c) and abs(c)<.25 for c in delta):
                raise RuntimeError(f'Invalid private rest displacement: {source_name}')
            bone_deltas[source_name]=delta
        if set(bone_deltas)!=set(x['source_bone'] for x in job['matched_roles']):
            raise RuntimeError('Rest-fit proposal does not cover every mapped standard bone')
        target_to_delta={source_map[key]:value for key,value in bone_deltas.items()}
        for key,target_name in accessory.items():
            if target_name not in target_to_delta:
                raise RuntimeError(f'No standard-bone offset for accessory parent: {key}')
            bone_deltas[key]=target_to_delta[target_name]
    ai_ops=[]
    ai_diagnostics={}
    if job.get('ai_fit_proposal'):
        proposal=json.loads(Path(job['ai_fit_proposal']).read_text(encoding='utf-8'))
        if (proposal.get('schema_version')!=2 or proposal.get('operation')!='edge_anchored_weight_relax'
                or proposal.get('game_install_authorized') is not False
                or not isinstance(proposal.get('operations'),list) or not 1<=len(proposal['operations'])<=8):
            raise RuntimeError('Invalid bounded local AI correction proposal')
        ai_ops=proposal['operations']
        if any(not isinstance(op,dict) for op in ai_ops):
            raise RuntimeError('Invalid AI correction entry')
        expected={f'[l0]vrm_{job["region"]}_{index:02}' for index in range(len(job['meshes']))}
        if any(op.get('mesh') not in expected for op in ai_ops):
            raise RuntimeError('AI proposal references unknown region mesh')
        paths=job.get('ai_diagnostic_paths',[])
        if not isinstance(paths,list) or not 1<=len(paths)<=3:
            raise RuntimeError('AI proposal requires private source diagnostic paths')
        for path in paths:
            report=json.loads(Path(path).read_text(encoding='utf-8'))
            name=report.get('mesh')
            if name in ai_diagnostics or name not in expected:
                raise RuntimeError('Invalid AI source diagnostic mesh')
            ai_diagnostics[name]=report
        if any(op['mesh'] not in ai_diagnostics for op in ai_ops):
            raise RuntimeError('AI proposal lacks corresponding motion diagnostic')
    textures=json.loads(Path(job['texture_map']).read_text(encoding='utf-8'))
    mat_map={m['material_name']:m['dds'] for m in textures['materials'] if m['dds']}
    addon(Path(job['addon']))
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    if bpy.ops.import_scene.gmd_skinned(filepath=str(original),strict=True,
                                         import_materials=True,import_hierarchy=True,
                                         import_objects=True)!={'FINISHED'}:
        raise RuntimeError('Target GMD strict import failed')
    scene=bpy.context.scene
    rig=next(o for o in scene.objects if o.type=='ARMATURE')
    originals=[o for o in scene.objects if o.type=='MESH']
    expected_bones=job.get('target_bone_count',358)
    if len(rig.data.bones)!=expected_bones or not originals:
        raise RuntimeError(f'Expected {expected_bones}-bone target GMD with template meshes')
    template=next((o for o in originals if o.data.materials and o.data.materials[0]
                   and o.data.materials[0].yakuza_data.inited),None)
    if template is None:
        raise RuntimeError('Target GMD lacks initialized shader template')
    material_templates=[(mat.yakuza_data.shader_name,mat) for obj in originals
        for mat in obj.data.materials if mat and mat.yakuza_data.inited]
    flags=template.yakuza_hierarchy_node_data.flags_json
    order=template.yakuza_hierarchy_node_data.sort_order
    collection=template.users_collection[0]
    to_load={}
    for entry in job['meshes']:
        blend=Path(entry['blend']).resolve(strict=True)
        to_load.setdefault(blend,[]).append(entry['object'])
    imported={}
    for blend,names in to_load.items():
        requested=list(names)
        with bpy.data.libraries.load(str(blend),link=False) as (src,dst):
            if not set(requested)<=set(src.objects):
                raise RuntimeError(f'Missing source mesh object in {blend}: {set(requested)-set(src.objects)}')
            dst.objects=list(requested)
        imported.update({(blend,name):obj for name,obj in zip(requested,dst.objects)})
    staged=[]
    for index,entry in enumerate(job['meshes']):
        source=imported[(Path(entry['blend']).resolve(),entry['object'])]
        if source is None or source.type!='MESH' or not source.data.uv_layers:
            raise RuntimeError(f'Invalid skinned mesh/UV: {entry}')
        obj=source.copy()
        obj.data=source.data.copy()
        obj.name=f'[l0]vrm_{job["region"]}_{index:02}'
        world=library_world(source)
        scales=world.to_scale()
        if any(abs(s-expected_scale)>1e-4 for s in scales):
            raise RuntimeError(f'Unexpected source world scale for {source.name}: {list(scales)}')
        obj.data.transform(world,shape_keys=True)
        solver_move=0.0
        if str(index) in job.get('mesh_offsets',{}):
            paths=job['mesh_offsets'][str(index)]
            source_data=json.loads(Path(paths['source_data']).read_text(encoding='utf-8'))
            fit=json.loads(Path(paths['solver_result']).read_text(encoding='utf-8'))
            if (fit.get('source_mesh')!=source.name or fit.get('game_install_authorized') is not False
                    or len(source_data['vertices'])!=len(obj.data.vertices)
                    or len(fit['offsets'])!=len(obj.data.vertices)):
                raise RuntimeError('Solver displacement does not match source mesh')
            offsets=[]
            for vertex,original,shift in zip(obj.data.vertices,source_data['vertices'],fit['offsets']):
                if ((vertex.co-Vector(original)).length>2e-5 or len(shift)!=3
                        or not all(type(v) in (int,float) and math.isfinite(v) for v in shift)):
                    raise RuntimeError('Stale/nonfinite solver displacement')
                vector=Vector(shift)
                if vector.length>.12:raise RuntimeError('Solver displacement exceeds 12cm')
                offsets.append(vector)
            solver_move=max(v.length for v in offsets)
            old=[v.co.copy() for v in obj.data.vertices]
            for vertex,delta in zip(obj.data.vertices,offsets):vertex.co+=delta
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    for vertex,delta in zip(key.data,offsets):vertex.co+=delta
            for edge in obj.data.edges:
                a,b=edge.vertices
                length=(old[a]-old[b]).length
                if length>1e-5:
                    ratio=(obj.data.vertices[a].co-obj.data.vertices[b].co).length/length
                    if not 1/1.5-1e-4<=ratio<=1.5+1e-4:
                        raise RuntimeError('Solver exceeds rest edge-stretch bound')
        obj.parent=None
        obj.matrix_world.identity()
        collection.objects.link(obj)
        obj.parent=rig
        obj.matrix_parent_inverse.identity()
        obj.matrix_world.identity()
        group_names=[g.name for g in source.vertex_groups]
        rest_alpha=0.0
        max_rest_move=0.0
        if rest_fit:
            offsets=[]
            for vertex in source.data.vertices:
                raw=[0.0,0.0,0.0]
                total=0.0
                for weight in vertex.groups:
                    if weight.weight<=1e-8:continue
                    name=group_names[weight.group]
                    if name not in bone_deltas:
                        raise RuntimeError(f'Missing rest displacement: {name}')
                    total+=weight.weight
                    for axis in range(3):raw[axis]+=weight.weight*bone_deltas[name][axis]
                if total<=1e-8:raise RuntimeError(f'Unweighted rest-fit vertex: {vertex.index}')
                offsets.append(tuple(value/total for value in raw))
            old=[v.co.copy() for v in obj.data.vertices]
            max_rest_move=max(math.sqrt(sum(x*x for x in v)) for v in offsets)
            def safe_scale(alpha):
                for edge in obj.data.edges:
                    a,b=edge.vertices
                    before=(old[a]-old[b]).length
                    if before<=1e-5:continue
                    dx=[old[a][i]-old[b][i]+alpha*(offsets[a][i]-offsets[b][i]) for i in range(3)]
                    after=math.sqrt(sum(x*x for x in dx))
                    ratio=after/before
                    if ratio>1.5 or ratio<1/1.5:return False
                return True
            lo,hi=0.0,1.0
            for _ in range(18):
                mid=(lo+hi)/2
                if safe_scale(mid):lo=mid
                else:hi=mid
            rest_alpha=lo
            for vertex,offset in zip(obj.data.vertices,offsets):
                vertex.co=[vertex.co[i]+rest_alpha*offset[i] for i in range(3)]
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    for vertex,offset in zip(key.data,offsets):
                        vertex.co=[vertex.co[i]+rest_alpha*offset[i] for i in range(3)]
        anatomical_report=None
        if job.get('anatomical_fit'):
            if rest_fit or job.get('mesh_offsets') or job.get('foot_fit_targets'):
                raise RuntimeError('Do not combine anatomical fit with older displacement solvers')
            points=[list(v.co) for v in obj.data.vertices]
            weights=[{group_names[w.group]:w.weight for w in v.groups} for v in source.data.vertices]
            corrected=fit_points(points,weights,job['anatomical_fit'])
            shifts=[Vector(b)-Vector(a) for a,b in zip(points,corrected)]
            for vertex,point in zip(obj.data.vertices,corrected): vertex.co=point
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    for vertex,shift in zip(key.data,shifts): vertex.co+=shift
            anatomical_report={'version':job['anatomical_fit']['version'],
                'max_move_m':max((v.length for v in shifts),default=0),
                'minimum_z_m':min(p[2] for p in corrected)}
        foot_alpha=0.0
        foot_move=0.0
        foot_binding=None
        foot_floor=None
        foot_targets=job.get('foot_fit_targets',[])
        foot_deltas=job.get('foot_joint_deltas',{})
        if foot_targets:
            if set(foot_targets)!=set(foot_deltas):
                raise RuntimeError('Foot-fit targets and measured deltas disagree')
            for target_name,delta in foot_deltas.items():
                if (target_name not in rig.data.bones or len(delta)!=3
                        or not all(math.isfinite(c) and abs(c)<=.25 for c in delta)):
                    raise RuntimeError(f'Invalid bounded foot correction: {target_name}')
            group_rows=[[(w.group,w.weight) for w in vertex.groups] for vertex in source.data.vertices]
            offsets=weighted_bone_offsets(group_rows,group_names,source_map,foot_deltas,foot_targets)
            coords=[tuple(vertex.co) for vertex in obj.data.vertices]
            edges=[tuple(edge.vertices) for edge in obj.data.edges]
            foot_alpha,corrected=bounded_offsets(coords,edges,offsets,max_stretch=1.5)
            foot_move=max((math.sqrt(sum((foot_alpha*x)**2 for x in offset)) for offset in offsets),default=0.0)
            if foot_move>0 and foot_alpha<.999:
                foot_binding=limiting_edge(coords,edges,offsets,foot_alpha,max_stretch=1.5)
                if foot_binding:
                    foot_binding['source_weights']=[
                        {group_names[w.group]:round(w.weight,4) for w in source.data.vertices[index].groups
                         if w.weight>.01} for index in foot_binding['vertices']]
            ground=job.get('ground_alignment',{})
            if source.name in ground.get('source_floor_meshes',[]):
                target_floor=ground.get('target_floor_m')
                if type(target_floor) not in (int,float) or not math.isfinite(target_floor):
                    raise RuntimeError('Invalid target floor in ground alignment')
                foot_floor={'before_m':round(min(point[2] for point in coords),6),
                    'after_m':round(min(point[2] for point in corrected),6),
                    'target_m':round(target_floor,6),
                    'remaining_delta_m':round(target_floor-min(point[2] for point in corrected),6)}
            for vertex,point in zip(obj.data.vertices,corrected):vertex.co=point
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    for index,vertex in enumerate(key.data):
                        vertex.co=[vertex.co[axis]+foot_alpha*offsets[index][axis] for axis in range(3)]
        core_weight=0.0
        accessory_weight=0.0
        for vertex in source.data.vertices:
            for group in vertex.groups:
                if group.weight>1e-8:
                    name=group_names[group.group]
                    if name not in source_map:
                        raise RuntimeError(f'Unmapped influence in {source.name}: {name}')
                    if name in accessory:
                        accessory_weight+=group.weight
                    else:
                        core_weight+=group.weight
        obj.vertex_groups.clear()
        groups={name:obj.vertex_groups.new(name=name) for name in sorted(set(source_map.values()))
                if name in rig.data.bones}
        if not groups:
            raise RuntimeError('No game target bones in rig')
        weight_rows=[]
        for vertex in source.data.vertices:
            weights={}
            for weight in vertex.groups:
                if weight.weight<=1e-8:continue
                target=source_map[group_names[weight.group]]
                if target not in groups:
                    raise RuntimeError(f'No GMD bone: {target}')
                weights[target]=weights.get(target,0)+weight.weight
            if sum(weights.values())<=1e-8:
                raise RuntimeError(f'Unweighted vertex: {source.name}/{vertex.index}')
            weight_rows.append(weights)
        ai_changed=[]
        for op in ai_ops:
            if not isinstance(op,dict) or set(op)!={'mesh','center_bone','radius_m','strength','iterations'}:
                raise RuntimeError('Unknown AI correction operation')
            bone=op['center_bone']
            radius,strength,iterations=op['radius_m'],op['strength'],op['iterations']
            if (not isinstance(op['mesh'],str) or not isinstance(bone,str) or bone not in rig.data.bones
                    or type(radius) not in (int,float) or type(strength) not in (int,float)
                    or not math.isfinite(radius) or not math.isfinite(strength)
                    or not .02<=radius<=.22 or not .05<=strength<=.65
                    or type(iterations) is not int or not 1<=iterations<=3):
                raise RuntimeError('AI correction exceeds allowed bounded parameters')
            if op['mesh']!=obj.name:
                continue
            diagnostic=ai_diagnostics[obj.name]
            edge=next((edge for edge in diagnostic.get('worst_edges',[])
                       if any(name==bone and value>.01 for weights in edge['weights'] for name,value in weights)),None)
            if edge is None or len(edge.get('rest_coords',[]))!=2:
                raise RuntimeError(f'No bad edge anchored to AI bone: {obj.name}/{bone}')
            coords=edge['rest_coords']
            if any(len(point)!=3 or not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<5
                                               for v in point) for point in coords):
                raise RuntimeError('Invalid private motion edge coordinates')
            center=Vector([(coords[0][i]+coords[1][i])/2 for i in range(3)])
            if min((v.co-center).length for v in obj.data.vertices)>.01:
                raise RuntimeError('AI edge anchor does not match private source geometry')
            neighbors=[set() for _ in weight_rows]
            for edge in obj.data.edges:
                a,b=edge.vertices
                neighbors[a].add(b);neighbors[b].add(a)
            positions=[(vertex.co-center).length for vertex in obj.data.vertices]
            touched=sum(distance<radius and bool(neighbors[v]) for v,distance in enumerate(positions))
            if touched==0:
                raise RuntimeError(f'AI bone sphere touches no vertices: {obj.name}/{bone}')
            for _ in range(iterations):
                updated=[]
                for v,weights in enumerate(weight_rows):
                    distance=positions[v]
                    if distance>=radius or not neighbors[v]:
                        updated.append(weights)
                        continue
                    factor=strength*(1-distance/radius)
                    result={key:(1-factor)*value for key,value in weights.items()}
                    portion=factor/len(neighbors[v])
                    for neighbor in neighbors[v]:
                        for key,value in weight_rows[neighbor].items():
                            result[key]=result.get(key,0)+portion*value
                    updated.append(result)
                weight_rows=updated
            ai_changed.append({'center_bone':bone,'vertices_in_sphere':touched,
                               'radius_m':radius,'strength':strength,'iterations':iterations})
        passes=job.get('weight_smooth_iterations',0)
        if type(passes) is not int or not 0<=passes<=5:
            raise RuntimeError('Experimental smoothing passes must be 0..5')
        if passes:
            neighbors=[set() for _ in weight_rows]
            for edge in obj.data.edges:
                a,b=edge.vertices
                neighbors[a].add(b)
                neighbors[b].add(a)
            for _ in range(passes):
                updated=[]
                for v,weights in enumerate(weight_rows):
                    if not neighbors[v]:
                        updated.append(weights)
                        continue
                    blend={k:0.5*w for k,w in weights.items()}
                    factor=0.5/len(neighbors[v])
                    for neighbor in neighbors[v]:
                        for key,value in weight_rows[neighbor].items():
                            blend[key]=blend.get(key,0)+factor*value
                    updated.append(blend)
                weight_rows=updated
        max_loss=0.0
        for vertex,weights in zip(source.data.vertices,weight_rows):
            total=sum(weights.values())
            ranked=sorted(weights.items(),key=lambda p:-p[1])
            loss=sum(w for _,w in ranked[4:])/total
            max_loss=max(max_loss,loss)
            if loss>.01:
                raise RuntimeError(f'Influence loss {loss:.2%} exceeds 1%')
            selected=ranked[:4]
            kept=sum(w for _,w in selected)
            for name,weight in selected:
                groups[name].add([vertex.index],weight/kept,'REPLACE')
        for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
        obj.modifiers.new('Target rig','ARMATURE').object=rig
        obj.yakuza_hierarchy_node_data.flags_json=flags
        obj.yakuza_hierarchy_node_data.sort_order=order
        uv=obj.data.uv_layers
        uv[0].name='UV_Primary'
        if len(uv)==1:uv.new(name='UV1_2_components',do_init=True)
        else:uv[1].name='UV1_2_components'
        for name in ('NormalW','TangentW','Color0','Color1','UV2_4_components','UV3_4_components'):
            if name not in obj.data.color_attributes:
                obj.data.color_attributes.new(name=name,type='FLOAT_COLOR',domain='CORNER')
        for name in ('NormalW','TangentW','Color0','Color1'):
            for v in obj.data.color_attributes[name].data:v.color=(1,1,1,1)
        names=[m.name if m else '' for m in source.data.materials]
        def base_material(name):
            if name in mat_map:return name
            base=re.sub(r'\.\d{3}$','',name)
            if base in mat_map:return base  # Blender duplicate suffix, not a new glTF material
            raise RuntimeError(f'Source material has no DDS mapping: {name}')
        material_keys=[base_material(m) for m in names]
        dummy_maps_applied=set()
        material_dummy_maps=[]
        if any(p.material_index>=len(names) for p in obj.data.polygons):
            raise RuntimeError(f'Polygon material slot out of range: {obj.name}')
        obj.data.materials.clear()
        for name in material_keys:
            filename=mat_map[name]
            image_path=Path(job['dds_dir'])/filename
            if not image_path.is_file():
                raise RuntimeError(f'Missing local DDS: {image_path}')
            source_region=entry.get('source_region',job['region'])
            template_shader,template_material=select_material_template(material_templates,source_region)
            mat=template_material.copy()
            mat.name=f'VRM_{job["region"]}_{index:02}_{len(obj.data.materials)}'
            shader=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree
                         and 'Yakuza Shader' in n.node_tree.name),None)
            if shader is None:
                raise RuntimeError('Selected template lacks Yakuza shader node')
            apply_matte_specular(shader)
            diffuse=shader.inputs.get('texture_diffuse')
            if not diffuse or not diffuse.links or not hasattr(diffuse.links[0].from_node,'image'):
                raise RuntimeError('Cannot wire target shader diffuse DDS')
            diffuse.links[0].from_node.image=bpy.data.images.load(str(image_path),check_existing=True)
            # Apply the four-slot dummy recipe to EVERY material, including
            # previously unlinked rt/rd sockets. Never silently keep native maps.
            dummy_slots=job.get('dummy_texture_slots',{})
            assigned=apply_dummy_maps(mat,shader,dummy_slots,job['dds_dir'],bpy.data.images.load)
            dummy_maps_applied.update(assigned)
            material_dummy_maps.append({'source_material':name,'material':mat.name,
                                        'diffuse':Path(filename).stem,'dummy_maps':assigned,
                                        'source_region':source_region,'template_shader':template_shader,
                                        'specular_rgb':[0,0,0]})
            obj.data.materials.append(mat)
        if obj.data.shape_keys and any((obj.data.vertices[v.index].co-
                obj.data.shape_keys.key_blocks[0].data[v.index].co).length>1e-5
                for v in obj.data.vertices):
            raise RuntimeError(f'Stale Basis for {obj.name}')
        if any(not all(math.isfinite(c) for c in v.co) for v in obj.data.vertices):
            raise RuntimeError(f'Nonfinite vertices: {obj.name}')
        staged.append({'source':source.name,'mesh':obj.name,'vertices':len(obj.data.vertices),
                       'faces':len(obj.data.polygons),'rest_fit_alpha':round(rest_alpha,5),
                       'max_proposed_rest_move_m':round(max_rest_move,6),'solver_max_displacement_m':round(solver_move,6),
                       'ai_corrections':ai_changed,'foot_fit_alpha':round(foot_alpha,5),
                       'foot_fit_max_move_m':round(foot_move,6),
                       'foot_fit_binding_edge':foot_binding,'foot_fit_floor':foot_floor,
                       'anatomical_fit':anatomical_report,
                       'dummy_maps_applied':sorted(dummy_maps_applied),
                       'dummy_maps_skipped':[],
                       'material_dummy_maps':material_dummy_maps,
                       'accessory_weight_fraction':round(accessory_weight/(core_weight+accessory_weight),4),
                       'max_influence_loss':max_loss})
    for old in originals:
        bpy.data.objects.remove(old,do_unlink=True)
    if sum(o.type=='MESH' for o in scene.objects)!=len(staged):
        raise RuntimeError('Export scene contains unexpected meshes')
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    if bpy.ops.export_scene.gmd_skinned(filepath=str(working),strict=True,
                                         bone_matrix_origin='FROM_TARGET_FILE')!={'FINISHED'}:
        raise RuntimeError('GMD strict export failed')
    verify=bpy.data.scenes.new('DRAGON_DRAFT_VERIFY')
    bpy.context.window.scene=verify
    before=set(bpy.data.objects)
    if bpy.ops.import_scene.gmd_skinned(filepath=str(working),strict=True,
                                         import_materials=True,import_hierarchy=True,
                                         import_objects=True)!={'FINISHED'}:
        raise RuntimeError('GMD strict reimport failed')
    added=set(bpy.data.objects)-before
    rigs=[o for o in added if o.type=='ARMATURE']
    meshes=[o for o in added if o.type=='MESH']
    if len(rigs)!=1 or len(rigs[0].data.bones)!=job.get('target_bone_count',358) or len(meshes)!=len(staged):
        raise RuntimeError(f'Invalid reimport rig/mesh count: {[len(r.data.bones) for r in rigs]}/{len(meshes)}')
    if any(not obj.data.uv_layers or not obj.data.materials or
           any(not v.groups or len(v.groups)>4 for v in obj.data.vertices)
           for obj in meshes):
        raise RuntimeError('Reimported mesh missing UV/material/skin weights')
    # Parse the actual exported file: successful Blender import alone does not
    # prove that all auxiliary references survived material export.
    from yk_gmd_blender.gmdlib.io import read_gmd_structures, read_abstract_scene_from_filedata_object
    from yk_gmd_blender.gmdlib.converters.common.to_abstract import FileImportMode, VertexImportMode
    from yk_gmd_blender.gmdlib.errors.error_reporter import StrictErrorReporter
    error=StrictErrorReporter(set())
    version,header,contents=read_gmd_structures(str(working),error)
    exported=read_abstract_scene_from_filedata_object(version,FileImportMode.SKINNED,
        VertexImportMode.IMPORT_VERTICES,contents,error)
    attributes=[mesh.attribute_set for node in exported.overall_hierarchy
                for mesh in getattr(node,'mesh_list',[])]
    dummy_verified=verify_dummy_references(attributes,job['dummy_texture_slots'])
    if any(list(a.material.origin_data.specular)!=[0,0,0]
           or any(tag in a.shader.name.lower() for tag in ('[eye]','[mouth]'))
           or a.shader.name.lower().startswith('sd_d')
           for a in attributes):
        raise RuntimeError('Exported material retained glossy specular or an eye/mouth template')
    return {'region':job['region'],'review_only':True,'strict_export_reimport':True,
            'dummy_recipe':'explicit-four-slot-v1','exported_dummy_maps_verified':True,
            'dummy_material_attribute_count':dummy_verified,
            'material_policy':'region-template-matte-v2','matte_specular_verified':True,
            'target_bones':job.get('target_bone_count',358),'source_mesh_count':len(staged),'reimport_mesh_count':len(meshes),
            'staged':staged,'has_accessory_collapse':any(s['accessory_weight_fraction']>0 for s in staged),
            'motion_checked':False,'appearance_checked':False,'game_install_changed':False}


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=2:raise SystemExit('expected -- job.json result.json')
    job=json.loads(Path(args[0]).read_text(encoding='utf-8'))
    result=run(job)
    Path(args[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('DRAGON_FULL_DRAFT_REGION_OK',job['region'])
