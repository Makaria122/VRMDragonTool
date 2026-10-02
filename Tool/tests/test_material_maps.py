import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um.dragon_material_maps import (DUMMY_SLOTS, apply_dummy_maps, verify_dummy_references,
                                    select_material_template, apply_matte_specular)


class Nodes:
    def __init__(self):
        self.created = []

    def new(self, kind):
        node = SimpleNamespace(label='', image=None, outputs={'Color': object()})
        self.created.append(node)
        return node


class Links:
    def new(self, output, socket):
        socket.links.append(output)

    def remove(self, link):
        pass


class DummyTests(unittest.TestCase):
    def test_region_templates_exclude_eye_and_matte_specular(self):
        eye, skin, hair, cloth = object(), object(), object(), object()
        candidates = [('sd_o1dzt[eye]', eye), ('sd_o1dzt[skin]', skin),
                      ('sd_c1dzt[hair]', hair), ('sd_o1dzt', cloth)]
        self.assertIs(select_material_template(candidates, 'hair')[1], hair)
        self.assertIs(select_material_template(candidates, 'face')[1], skin)
        self.assertIs(select_material_template(candidates, 'tops')[1], cloth)
        self.assertIs(select_material_template(candidates[:2], 'tops')[1], skin)
        decals = [('sd_d1dzt', object()), ('sd_o1dzt[mouth]', object())]
        self.assertIs(select_material_template(decals + candidates, 'tops')[1], cloth)
        with self.assertRaises(RuntimeError):
            select_material_template(decals, 'tops')
        with self.assertRaises(RuntimeError):
            select_material_template(candidates[:1], 'tops')
        socket = SimpleNamespace(default_value=(1, 1, 1, 1))
        apply_matte_specular(SimpleNamespace(inputs={'Specular color': socket}))
        self.assertEqual(socket.default_value, (0, 0, 0, 1))

    def test_unlinked_slots_all_receive_dummies_and_diffuse_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slots = {s: s + '.dds' for s in DUMMY_SLOTS}
            for name in slots.values():
                (root / name).write_bytes(b'DDS synthetic-test-only')
            sockets = {s: SimpleNamespace(links=[]) for s in DUMMY_SLOTS}
            sockets['texture_diffuse'] = SimpleNamespace(links=['original-diffuse'])
            material = SimpleNamespace(node_tree=SimpleNamespace(nodes=Nodes(), links=Links()))
            shader = SimpleNamespace(inputs=sockets)
            result = apply_dummy_maps(material, shader, slots, root,
                                      lambda path, check_existing: SimpleNamespace(filepath=path))
            self.assertEqual(set(result), set(DUMMY_SLOTS))
            self.assertTrue(all(len(sockets[s].links) == 1 for s in DUMMY_SLOTS))
            self.assertEqual(sockets['texture_diffuse'].links, ['original-diffuse'])
            self.assertEqual(len(material.node_tree.nodes.created), 4)

    def test_export_reference_mismatch_and_incomplete_recipe_fail(self):
        slots = {s: 'private_' + s + '.dds' for s in DUMMY_SLOTS}
        attr = SimpleNamespace(**{s: Path(n).stem for s, n in slots.items()})
        self.assertEqual(verify_dummy_references([attr, attr], slots), 2)
        attr.texture_rt = None
        with self.assertRaisesRegex(RuntimeError, 'texture_rt'):
            verify_dummy_references([attr], slots)
        with self.assertRaises(RuntimeError):
            verify_dummy_references([attr], {})


if __name__ == '__main__':
    unittest.main()
