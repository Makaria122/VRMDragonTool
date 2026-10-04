import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'um'))
from dragon_material_maps import select_material_template


class TemplateChoiceTests(unittest.TestCase):
    CANDIDATES = [('sd_o1dzt_m2t[skin]', 'skin'), ('sd_c1dzt[hair][vcol][ao]', 'hair'),
                  ('sd_o1dzt_m2dzt_h2dz', 'suit'), ('sd_o1dzt', 'plain'), ('sd_o1dzt[eye]', 'eye')]

    def test_clothing_uses_the_plain_shader_not_the_characters_own_cloth_shader(self):
        # Kiryu's suit shader kept native roughness/reflection maps and made avatars look black in dark scenes.
        self.assertEqual(select_material_template(self.CANDIDATES, 'tops'), ('sd_o1dzt', 'plain'))

    def test_clothing_falls_back_when_the_character_has_no_plain_shader(self):
        candidates = [c for c in self.CANDIDATES if c[0] != 'sd_o1dzt']
        self.assertEqual(select_material_template(candidates, 'tops')[0], 'sd_o1dzt_m2dzt_h2dz')

    def test_hair_and_face_keep_their_own_templates(self):
        self.assertEqual(select_material_template(self.CANDIDATES, 'hair')[0], 'sd_c1dzt[hair][vcol][ao]')
        self.assertEqual(select_material_template([('sd_o1dzt_m2t[skin]', 's'), ('sd_o1dzt', 'p')], 'face')[0],
                         'sd_o1dzt_m2t[skin]')

    def test_eye_and_mouth_shaders_are_never_chosen(self):
        with self.assertRaises(RuntimeError):
            select_material_template([('sd_o1dzt[eye]', 'e'), ('sd_o1dzt[mouth]', 'm')], 'tops')


if __name__ == '__main__':
    unittest.main()
