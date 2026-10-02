"""Per-batch measured skeleton grouping, not a file-name compatibility guess."""
import copy
import hashlib
import json
import math


def signature(snapshot):
    def quantize(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError('Nonfinite skeleton transform')
            return round(value, 7)
        if isinstance(value, list):
            return [quantize(v) for v in value]
        if isinstance(value, dict):
            return {k: quantize(v) for k,v in sorted(value.items())}
        return value
    return hashlib.sha256(json.dumps(quantize(snapshot),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def equivalent(left, right, tolerance=1e-7):
    if type(left) != type(right) and not (type(left) in (int,float) and type(right) in (int,float)):
        return False
    if type(left) in (int,float):
        return math.isfinite(left) and math.isfinite(right) and abs(left-right)<=tolerance
    if isinstance(left, dict):
        return left.keys()==right.keys() and all(equivalent(left[k],right[k],tolerance) for k in left)
    if isinstance(left, list):
        return len(left)==len(right) and all(equivalent(a,b,tolerance) for a,b in zip(left,right))
    return left==right


def measured_group(checked, vrm_hash, target_id):
    references=checked['blender_inspection']['references']
    if not references or any(len(row.get('skeletons',[]))!=1 for row in references.values()):
        raise ValueError('Expected one measured reference skeleton per role')
    snapshots={role:row['skeletons'][0] for role,row in references.items()}
    key=hashlib.sha256(json.dumps({'version':'skeleton-preparation-v1','person':target_id.split('__')[0],
        'vrm':vrm_hash,'roles':{r:signature(s) for r,s in snapshots.items()}},sort_keys=True).encode()).hexdigest()
    return key,snapshots


def reuse_profile(profile, inventory, fit_plan):
    """Reuse AI labels; refresh measured floor/foot values, never reuse outfit floor blindly."""
    from um.dragon_local_profile import _validate
    correction=inventory['ground_alignment']['measured_correction_m']
    raw={'mesh_regions':copy.deepcopy(profile['mesh_regions']),
         'accessory_parent_hints':copy.deepcopy(profile['accessory_parent_hints']),
         'ground_action':'raise' if correction>.005 else 'lower' if correction<-.005 else 'keep',
         'foot_fit_targets':sorted(r['target_bone'] for r in inventory.get('foot_alignment',[])
                                   if .04<float(r.get('distance_m',0))<=.25)}
    result=_validate(raw,inventory,fit_plan)
    result['profile_method']='skeleton_group_reuse'
    result['model']=profile.get('model',result['model'])
    result['coverage_adjustments']=copy.deepcopy(profile.get('coverage_adjustments',[]))
    result['ground_alignment']['action_method']='deterministic_refresh_of_measured_floor'
    if inventory.get('joint_anchors'):
        from um.dragon_anatomical_fit import recipe
        current=recipe(inventory)
        # Reuse an identical solver recipe; recompute if fresh anchors demand it.
        result['anatomical_recipe_reused']=profile.get('anatomical_fit')==current
        result['anatomical_fit']=copy.deepcopy(profile.get('anatomical_fit')) if result['anatomical_recipe_reused'] else current
    return result
