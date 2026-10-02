import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from um.dragon_targets import get_target, target_references
from um.dragon_variants import ROWS, variants_for, replacement_ownership, run_batch, availability
from um.dragon_textures import texture_namespace


class VariantTests(unittest.TestCase):
    def test_explicit_recipes_and_cutscene_layout(self):
        for base,key,*_ in ROWS:
            t=get_target(base+'__'+key)
            self.assertEqual(t.bone_count,get_target(base).bone_count)
            self.assertEqual(sorted(r for s in t.slots for r in s.source_regions),['face','hair','tops'])
            self.assertEqual(t.slots[0].key,'tops')
        t=get_target('kaito__cutscene')
        self.assertEqual([s.stem for s in t.slots],['c_cm_x_kaito','c_cm_f_kaito'])
        self.assertEqual(t.slots[1].source_regions,('face','hair'))
        with self.assertRaises(ValueError):get_target('kaito__boy')
        self.assertEqual(variants_for('sawa'),['sawa'])
        self.assertEqual(variants_for('kuwana'),['kuwana','kuwana__event_c04','kuwana__event_c10'])
        owned=replacement_ownership(variants_for('kuwana'))
        self.assertEqual(len(owned),4)
        self.assertEqual(owned['chara/face/c_cm_f_kuwana/c_cm_f_kuwana.gmd']['owner'],'kuwana')
        self.assertEqual(get_target('kuwana__event_c10').slots[0].stem,'c_cm_x_kuwana_c10bd01')

    def test_shared_path_has_one_predeclared_owner(self):
        owners=replacement_ownership(['kaito','kaito__cutscene','kaito__suit'])
        self.assertEqual(len(owners),4)
        face='chara/face/c_cm_f_kaito/c_cm_f_kaito.gmd'
        self.assertEqual(owners[face]['owner'],'kaito__cutscene')
        with patch('um.dragon_targets.get_target') as get:
            from um.dragon_targets import Target, ExportSlot
            slot=ExportSlot('tops','tops','same',('tops','face','hair'),'tops')
            get.side_effect=[Target('a','a','same',1,{'tops':'a.gmd'},(slot,),''),
                             Target('b','b','same',1,{'tops':'b.gmd'},(slot,),'')]
            with self.assertRaises(ValueError):replacement_ownership(['a','b'])

    def test_variant_shares_dds_namespace_but_cache_id_is_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            vrm=Path(temp)/'x.vrm';vrm.write_bytes(b'avatar')
            self.assertEqual(texture_namespace(vrm,'kaito'),texture_namespace(vrm,'kaito__cutscene'))
            self.assertNotEqual(get_target('kaito').id,get_target('kaito__cutscene').id)

    def test_batch_combines_owned_paths_only_and_reports_partial_motion(self):
        bundle=Path(__file__).resolve().parents[2]
        keys=['kaito','kaito__cutscene','kaito__suit']
        def fake_run(vrm,refs,blender,addon,action,baseline,out,dummy,progress,target_id,profile_root,preparation_cache):
            mod=Path(out)/'ReviewPack/Mods/fake';mod.mkdir(parents=True)
            (mod/'mod-meta.yaml').write_text('name: Test\n',encoding='utf-8')
            t=get_target(target_id)
            for slot in t.slots:
                p=mod/'chara'/slot.region/slot.stem/(slot.stem+'.gmd')
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(target_id.encode())
            d=mod/'chara/dds_hires/00/same.dds';d.parent.mkdir(parents=True);d.write_bytes(b'DDS identical')
            return {'mod_folder':str(mod),'candidate_status':'MOTION_CHECK_FAILED'}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'batch'
            with patch('um.dragon_variants.availability',return_value=[{'id':k,'ready':True} for k in keys]),patch('um.dragon_oneclick.run',side_effect=fake_run):
                result=run_batch('vrm',target_references('kaito',bundle/'PrivateData'),'b','a','act','baseline',out,'dummy',target_id='kaito')
            mod=Path(result['mod_folder'])
            self.assertEqual(len(list(mod.rglob('*.gmd'))),4)
            face=mod/'chara/face/c_cm_f_kaito/c_cm_f_kaito.gmd'
            self.assertEqual(face.read_bytes(),b'kaito__cutscene')
            self.assertEqual(result['status'],'VARIANT_PACK_MOTION_CHECK_FAILED')
            self.assertFalse(result['motion_quality_passed'])
            self.assertTrue((mod/'VARIANT_REVIEW_WARNING.txt').is_file())
            self.assertTrue(all(r['status']=='MOTION_CHECK_FAILED' for r in result['variants']))
            self.assertFalse(result['runtime_switch_verified'])
            self.assertFalse(result['game_install_changed'])
            self.assertTrue((out/'variant-coverage.json').is_file())

    def test_readiness_requires_current_reference_hashes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            private=Path(temp)
            key='kaito__cutscene'
            hashes={}
            for target in ('kaito',key):
                for relative in get_target(target).reference_files.values():
                    p=private/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'reference')
                    hashes[relative]=hashlib.sha256(b'reference').hexdigest()
            m=private/'TargetDiscovery/variant_reference_validation.json';m.parent.mkdir()
            m.write_text(json.dumps({'verified_variants':[key],'reference_sha256':hashes}))
            self.assertTrue(next(r for r in availability('kaito',private) if r['id']==key)['ready'])
            p=private/get_target(key).reference_files['tops'];p.write_bytes(b'changed')
            self.assertFalse(next(r for r in availability('kaito',private) if r['id']==key)['ready'])

    def test_failure_does_not_publish_combined_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'batch'
            bundle=Path(__file__).resolve().parents[2]
            with patch('um.dragon_variants.availability',return_value=[{'id':'kaito','ready':True}]),patch('um.dragon_oneclick.run',side_effect=RuntimeError('export failed')):
                with self.assertRaises(RuntimeError):
                    run_batch('v',target_references('kaito',bundle/'PrivateData'),'b','a','act','base',out,'d',target_id='kaito')
            self.assertEqual(json.loads((out/'variant-coverage.json').read_text())['status'],'VARIANT_BATCH_FAILED')
            self.assertFalse((out/'ReviewPack').exists())


if __name__=='__main__':unittest.main()
