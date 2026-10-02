import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from um.dragon_asset_catalog import resolve_references,AssetCatalogError
from um.dragon_targets import target_references,get_target
from um.dragon_variants import availability

class AssetCatalogTests(unittest.TestCase):
    def test_flat_and_nested_identical_duplicates(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'nested').mkdir()
            for relative in get_target('kuwana').reference_files.values():
                name=Path(relative).name
                (root/name).write_bytes(b'test');(root/'nested'/name).write_bytes(b'test')
            refs=target_references('kuwana',source_root=root)
            self.assertEqual(set(refs),{'tops','face','hair'})
            self.assertEqual(Path(refs['face']),Path(refs['hair']))
            rows=availability('kuwana',source_root=root)
            self.assertTrue(rows[0]['ready']);self.assertFalse(rows[0]['validated'])
            self.assertFalse(rows[1]['ready']);self.assertFalse(rows[2]['ready'])
            self.assertEqual((root/Path(get_target('kuwana').reference_files['tops']).name).read_bytes(),b'test')

    def test_sawa_special_references_found_without_private_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for stem in ('c_aw_sawa','c_aw_sawa_18','c_aw_sawa_dead','c_aw_sawa_sit'):
                (root/(stem+'.gmd')).write_bytes(b'synthetic reference')
            (root/'c_cw_f_amasawa.gmd').write_bytes(b'other person')
            rows=availability('sawa',source_root=root)
            self.assertEqual(len(rows),4)
            self.assertTrue(all(r['ready'] and not r['validated'] for r in rows))
            self.assertEqual(Path(target_references('sawa__sitting',source_root=root)['tops']).name,'c_aw_sawa_sit.gmd')

    def test_differing_duplicate_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'other').mkdir()
            (root/'a.gmd').write_bytes(b'a');(root/'other/a.gmd').write_bytes(b'b')
            with self.assertRaises(AssetCatalogError):resolve_references({'tops':'a.gmd'},root)

    def test_missing_never_substitutes_other_basename(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'other.gmd').write_bytes(b'other')
            with self.assertRaises(AssetCatalogError):resolve_references({'tops':'missing.gmd'},root)
            self.assertEqual(resolve_references({'tops':'missing.gmd'},root,allow_missing=True),{})

if __name__=='__main__':unittest.main()
