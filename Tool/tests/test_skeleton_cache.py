import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from um.dragon_skeleton_cache import equivalent, signature, measured_group, reuse_profile


class SkeletonCacheTests(unittest.TestCase):
    def snapshot(self):
        return {'rig_world':[1.0,0.0], 'bones':[{'name':'neck','parent':None,'matrix':[1.0,0.0],
                                             'head':[0.0,1.0,0.0],'tail':[0.0,1.1,0.0]}]}

    def test_signature_changes_for_name_parent_matrix_tail_or_rig_transform(self):
        a=self.snapshot()
        for field in ('name','parent','matrix','tail','rig_world'):
            b=copy.deepcopy(a)
            if field=='rig_world':b[field][0]+=0.1
            elif field in ('name','parent'):b['bones'][0][field]='different'
            else:b['bones'][0][field][0]+=0.1
            self.assertNotEqual(signature(a),signature(b))
            self.assertFalse(equivalent(a,b))
        b=copy.deepcopy(a);b['bones'][0]['head'][0]+=1e-9
        self.assertEqual(signature(a),signature(b))
        self.assertTrue(equivalent(a,b))
        b['bones'][0]['head'][0]=float('nan')
        with self.assertRaises(ValueError):signature(b)
        self.assertFalse(equivalent(a,b))

    def test_group_key_shared_by_variants_not_other_vrm_or_person(self):
        s=self.snapshot();checked={'blender_inspection':{'references':{
            r:{'skeletons':[s]} for r in ('tops','face','hair')}}}
        key,_=measured_group(checked,'vrmhash','kaito__cutscene')
        self.assertEqual(key,measured_group(checked,'vrmhash','kaito__suit')[0])
        self.assertNotEqual(key,measured_group(checked,'other','kaito__suit')[0])
        self.assertNotEqual(key,measured_group(checked,'vrmhash','tesso')[0])
        other=copy.deepcopy(checked)
        other['blender_inspection']['references']['face']['skeletons'][0]['tail']=[1.0]
        self.assertNotEqual(key,measured_group(other,'vrmhash','kaito')[0])

    def test_shared_labels_refresh_outfit_floor_without_calling_ai(self):
        profile={'mesh_regions':{'body':'tops','face':'face','hair':'hair'},
                 'accessory_parent_hints':[], 'ground_alignment':{'measured_correction_m':0.1}}
        items={'meshes':[{'object':n,'region':r} for n,r in profile['mesh_regions'].items()],
               'ground_alignment':{'measured_correction_m':-0.02},
               'unknown_weight_groups':[],'foot_alignment':[]}
        result=reuse_profile(profile,items,{'matched_roles':[],'accessory_parent_hints':[]})
        self.assertEqual(result['profile_method'],'skeleton_group_reuse')
        self.assertEqual(result['mesh_regions'],profile['mesh_regions'])
        self.assertEqual(result['ground_alignment']['local_ai_action'],'lower')
        self.assertEqual(result['ground_alignment']['recommended_vertical_offset_m'],-0.02)
        self.assertEqual(profile['ground_alignment']['measured_correction_m'],0.1)


if __name__=='__main__':unittest.main()
