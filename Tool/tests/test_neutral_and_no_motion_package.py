import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from um.dragon_neutral_maps import RECIPES, dds_bytes,write_neutral_maps
from um.dragon_mod_package import package
from um.dragon_targets import get_target

class NeutralAndNoMotionTests(unittest.TestCase):
    def test_beta_no_action_does_not_index_or_format_absent_poses(self):
        import hashlib
        from unittest.mock import patch
        from um.dragon_beta import build,GENERIC_SCHEMA
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);template=root/'template';template.mkdir()
            vrm=root/'avatar.vrm';vrm.write_bytes(b'synthetic')
            blender=root/'blender.exe';blender.touch()
            addon=root/'addon/yk_gmd_blender';addon.mkdir(parents=True);(addon/'__init__.py').touch()
            original=root/'c_am_kaito.gmd';original.write_bytes(b'synthetic reference')
            textures=root/'textures';textures.mkdir()
            texmap=root/'textures.json';texmap.write_text(json.dumps({'images':[]}))
            (template/'tops_job.json').write_text(json.dumps({'original_gmd':str(original),'meshes':[],
                'target_bone_count':285,'texture_map':str(texmap),'dds_dir':str(textures)}))
            profile=root/'profile.json';profile.write_text(json.dumps({'schema':GENERIC_SCHEMA,
                'source_vrm':str(vrm),'vrm_sha256':hashlib.sha256(vrm.read_bytes()).hexdigest(),
                'template_dir':str(template),'target_id':'kaito','action_blend':None}))
            def fake_run(exe,script,args,progress):
                self.assertNotIn('pose',script.stem)
                result={'strict_export_reimport':True,'source_mesh_count':1,'rest_geometry_verified':True}
                args[-1].write_text(json.dumps(result))
            with patch('um.dragon_beta._run',side_effect=fake_run):
                result=build(profile,vrm,root/'candidate',blender,addon.parent)
            self.assertEqual(result['status'],'MOTION_NOT_RUN')
            self.assertFalse(result['motion_quality_passed']);self.assertEqual(result['pose_samples'],0)

    def test_neutral_dds_header_recipe_and_pillow_loader(self):
        import struct
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            maps=write_neutral_maps(Path(t)/'maps')
            from um.dragon_oneclick import DUMMY_SOURCES
            self.assertTrue(all((Path(t)/'maps'/name).is_file() for name in DUMMY_SOURCES.values()))
            for key,color in RECIPES.items():
                path=Path(t)/f'{key}.dds';path.write_bytes(dds_bytes(color))
                self.assertEqual(path.read_bytes()[:4],b'DDS ')
                self.assertEqual(struct.unpack_from('<I',path.read_bytes(),20)[0],16)
                self.assertEqual(struct.unpack_from('<I',path.read_bytes(),108)[0],0x1000)
                with Image.open(path) as image:
                    self.assertEqual(image.size,(4,4))
                    self.assertEqual(image.convert('RGBA').getpixel((0,0)),color)

    def test_generated_maps_keep_legacy_bc1_and_bgra_layouts(self):
        import struct
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            maps=write_neutral_maps(t)
            for name,expected_length,mips in [('multi',152,3),('white',136,0),('normal',192,0)]:
                data=maps[name].read_bytes()
                self.assertEqual(len(data),expected_length)
                self.assertEqual(struct.unpack_from('<I',data,28)[0],mips)
                self.assertEqual(data[84:88],b'\0'*4 if name=='normal' else b'DXT1')
                with Image.open(maps[name]) as image:
                    self.assertEqual(image.convert('RGBA').getcolors(),[(16,RECIPES[name])])
            normal=maps['normal'].read_bytes()
            self.assertEqual(struct.unpack_from('<4I',normal,92),(0xff0000,0xff00,0xff,0xff000000))
            self.assertEqual(normal[128:132],bytes((255,128,128,255)))
        with self.assertRaises(ValueError):dds_bytes((0,0,0,0),encoding='bc1')

    def test_no_motion_strict_candidate_can_be_packaged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);candidate=root/'candidate';candidate.mkdir();target=get_target('yagami')
            for slot in target.slots:
                path=candidate/'chara'/slot.region/slot.stem/(slot.stem+'.gmd');path.parent.mkdir(parents=True)
                path.write_bytes(b'GMD strict synthetic test payload'*8)
            texture=candidate/'chara/dds_hires/00/neutral.dds';texture.parent.mkdir(parents=True)
            texture.write_bytes(dds_bytes(RECIPES['white']))
            (candidate/'status.json').write_text(json.dumps({'status':'MOTION_NOT_RUN','motion_validation':'MOTION_NOT_RUN',
                'motion_quality_passed':False,'manual_review_required':True,'target_id':'yagami',
                'strict_reimport_regions':len(target.slots),'source_mesh_count':len(target.slots),'game_install_changed':False}))
            result=package(candidate,root/'pack','Synthetic no motion')
            self.assertEqual(result['status'],'MODS_FORMAT_READY')
            status=json.loads((root/'pack/status.json').read_text())
            self.assertEqual(status['source_verdict'],'MOTION_NOT_RUN')
            self.assertFalse(status['game_install_changed'])

if __name__=='__main__':unittest.main()
