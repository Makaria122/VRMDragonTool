"""No game files: synthetic GLB materials and an embedded 4x4 PNG."""
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from um.dragon_textures import extract, texture_namespace


def synthetic_vrm(path, color):
    image = io.BytesIO()
    Image.new('RGBA', (4, 4), color).save(image, format='PNG')
    blob = image.getvalue()
    doc = {'asset': {'version': '2.0'},
           'bufferViews': [{'byteOffset': 0, 'byteLength': len(blob)}],
           'images': [{'mimeType': 'image/png', 'bufferView': 0}],
           'textures': [{'source': 0}],
           'materials': [{'name': 'Hair', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}},
                         {'name': 'Flat', 'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 0, 1]}}]}
    data = json.dumps(doc).encode('utf-8')
    data += b' ' * (-len(data) % 4)
    blob += b'\0' * (-len(blob) % 4)
    chunks = struct.pack('<I4s', len(data), b'JSON') + data + struct.pack('<I4s', len(blob), b'BIN\0') + blob
    path.write_bytes(b'glTF' + struct.pack('<II', 2, len(chunks) + 12) + chunks)


class NamespaceTests(unittest.TestCase):
    def test_content_and_character_isolation_and_manifest_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / 'a.vrm', root / 'b.vrm'
            synthetic_vrm(a, (255, 0, 0, 255))
            synthetic_vrm(b, (0, 255, 0, 255))
            before = a.read_bytes()
            ma = extract(a, root / 'out-a', target_id='yagami')
            mb = extract(b, root / 'out-b', target_id='kaito')
            names_a = {x['filename'] for x in ma['images']}
            names_b = {x['filename'] for x in mb['images']}
            self.assertFalse(names_a & names_b)
            self.assertNotEqual(texture_namespace(a, 'kaito'), texture_namespace(a, 'yagami'))
            self.assertNotEqual(texture_namespace(a, 'yagami'), texture_namespace(b, 'yagami'))
            self.assertEqual(texture_namespace(a, 'yagami'), ma['texture_namespace'])
            for row in ma['materials']:
                self.assertIn(row['dds'], names_a)
                self.assertTrue((root / 'out-a' / row['dds']).is_file())
                self.assertLess(len(Path(row['dds']).stem), 30)
            self.assertEqual(a.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
