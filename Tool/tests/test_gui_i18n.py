import ast
import glob
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_i18n as i18n
from um import dragon_theme as theme
from um.dragon_i18n_ja import JA

GUI_FILES = sorted(glob.glob(str(Path(__file__).resolve().parents[1] / 'um' / 'gui' / '*.py')))
FIELD = re.compile(r'\{[^{}]*\}')


def literal_keys():
    keys = {}
    for path in GUI_FILES:
        tree = ast.parse(Path(path).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys.setdefault(node.args[0].value, Path(path).name)
    return keys


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('en')

    def test_every_text_the_gui_shows_has_a_japanese_translation(self):
        missing = {k: f for k, f in literal_keys().items() if k not in JA}
        missing.update({k: 'DYNAMIC_KEYS' for k in i18n.DYNAMIC_KEYS if k not in JA})
        self.assertEqual(missing, {}, 'add these to um/dragon_i18n_ja.py')

    def test_the_japanese_dictionary_has_no_leftovers(self):
        used = set(literal_keys()) | set(i18n.DYNAMIC_KEYS)
        self.assertEqual(sorted(k for k in JA if k not in used), [])

    def test_placeholders_match_between_english_and_japanese(self):
        bad = [k for k, v in JA.items() if sorted(FIELD.findall(k)) != sorted(FIELD.findall(v))]
        self.assertEqual(bad, [])

    def test_no_translation_is_empty_or_unchanged_english_by_accident(self):
        same = [k for k, v in JA.items() if k == v and k not in ('English', 'Python', 'Blender', 'VRM → DDS')]
        self.assertEqual(same, [])
        self.assertEqual([k for k, v in JA.items() if not v.strip()], [])

    def test_tr_translates_formats_and_falls_back(self):
        i18n.set_language('ja')
        self.assertEqual(i18n.tr('Close'), '閉じる')
        self.assertIn('3', i18n.tr('Deleted {0} file(s).', 3))
        self.assertEqual(i18n.tr('A text nobody translated {0}', 5), 'A text nobody translated 5')
        i18n.set_language('en')
        self.assertEqual(i18n.tr('Close'), 'Close')
        self.assertEqual(i18n.tr('Deleted {0} file(s).', 3), 'Deleted 3 file(s).')

    def test_language_choice_and_a_broken_template_never_raise(self):
        self.assertEqual(i18n.resolve('ja'), 'ja')
        self.assertEqual(i18n.resolve('xx'), 'en')
        self.assertIn(i18n.resolve('auto'), ('en', 'ja'))
        i18n.set_language('ja')
        self.assertIsInstance(i18n.tr('Deleted {0} file(s).'), str)  # missing argument


class ThemeTests(unittest.TestCase):
    def test_both_palettes_define_the_same_colours(self):
        self.assertEqual(set(theme.PALETTES['light']), set(theme.PALETTES['dark']))

    def test_text_is_readable_on_its_background(self):
        def luminance(color):
            r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

        def contrast(a, b):
            la, lb = sorted((luminance(a), luminance(b)), reverse=True)
            return (la + 0.05) / (lb + 0.05)
        for mode, p in theme.PALETTES.items():
            for fg, bg in (('fg', 'bg'), ('fg', 'surface'), ('fg', 'field'), ('fg', 'sidebar'), ('muted', 'bg'),
                           ('accent_fg', 'accent'), ('select_fg', 'select_bg')):
                self.assertGreaterEqual(contrast(p[fg], p[bg]), 4.5, f'{mode}: {fg} on {bg}')

    def test_resolve_modes(self):
        self.assertEqual(theme.resolve('light'), 'light')
        self.assertEqual(theme.resolve('dark'), 'dark')
        self.assertIn(theme.resolve('system'), ('light', 'dark'))
        self.assertEqual(theme.resolve('nonsense'), 'light')


if __name__ == '__main__':
    unittest.main()
