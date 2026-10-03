import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_textures as textures
from um.dragon_textures import TextureError, extract, fit_for_dxt


def encode(size, fmt='PNG', color=(200, 40, 40, 255)):
    buffer = io.BytesIO()
    image = Image.new('RGBA', size, color)
    (image.convert('RGB') if fmt == 'JPEG' else image).save(buffer, format=fmt)
    return buffer.getvalue()


def make_glb(path, blobs, mime='image/png'):
    data = b''
    views = []
    for blob in blobs:
        views.append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(blob)})
        data += blob + b'\0' * (-len(blob) % 4)
    gltf = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(data)}], 'bufferViews': views,
            'images': [{'mimeType': mime, 'bufferView': i} for i in range(len(blobs))],
            'textures': [{'source': i} for i in range(len(blobs))],
            'materials': [{'name': f'm{i}', 'pbrMetallicRoughness': {'baseColorTexture': {'index': i}}}
                          for i in range(len(blobs))]}
    js = json.dumps(gltf).encode()
    js += b' ' * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(data)
    path.write_bytes(b'glTF' + struct.pack('<II', 2, total) + struct.pack('<I4s', len(js), b'JSON') + js
                     + struct.pack('<I4s', len(data), b'BIN\0') + data)


class TextureSizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_extract(self, blobs, mime='image/png'):
        vrm = self.root / 'a.vrm'
        make_glb(vrm, blobs, mime)
        return extract(vrm, self.root / 'out')

    def test_fit_rounds_up_to_multiples_of_four(self):
        self.assertEqual(fit_for_dxt(Image.new('RGBA', (10, 6))).size, (12, 8))
        self.assertEqual(fit_for_dxt(Image.new('RGBA', (1, 1))).size, (4, 4))
        same = Image.new('RGBA', (16, 8))
        self.assertIs(fit_for_dxt(same), same)

    def test_large_images_are_scaled_down_keeping_the_aspect(self):
        self.assertEqual(fit_for_dxt(Image.new('RGBA', (8192, 1024))).size, (4096, 512))
        self.assertEqual(fit_for_dxt(Image.new('RGBA', (4100, 20))).size, (4096, 20))

    def test_odd_sized_image_now_converts_and_the_change_is_recorded(self):
        result = self.run_extract([encode((10, 6)), encode((16, 8))])
        first, second = result['images']
        self.assertEqual((first['width'], first['height']), (12, 8))
        self.assertEqual(first['resized_from'], [10, 6])
        self.assertNotIn('resized_from', second)
        for item in result['images']:
            with Image.open(self.root / 'out' / item['filename']) as dds:
                self.assertEqual(dds.size, (item['width'], item['height']))
                self.assertEqual(dds.size[0] % 4 + dds.size[1] % 4, 0)

    def test_big_texture_is_written_at_most_4096(self):
        result = self.run_extract([encode((4100, 20))])
        self.assertEqual(result['images'][0]['width'], 4096)
        self.assertEqual(result['images'][0]['resized_from'], [4100, 20])

    def test_jpeg_and_webp_are_accepted(self):
        self.assertEqual(self.run_extract([encode((9, 9), 'JPEG', (200, 40, 40))], 'image/jpeg')['images'][0]['width'], 12)
        (self.root / 'out').rename(self.root / 'out1')
        self.assertEqual(self.run_extract([encode((9, 9), 'WEBP')], 'image/webp')['images'][0]['width'], 12)

    def test_absurdly_large_images_and_other_formats_are_still_refused(self):
        with self.assertRaises(TextureError):
            self.run_extract([encode((textures.MAX_SOURCE_SIDE + 8, 4))])
        (self.root / 'out').exists() and (self.root / 'out').rename(self.root / 'out_failed')
        with self.assertRaises(TextureError):
            self.run_extract([encode((8, 8), 'GIF')])

    def test_flat_colour_materials_still_work(self):
        vrm = self.root / 'flat.vrm'
        make_glb(vrm, [encode((8, 8))])
        gltf_materials = {'asset': {'version': '2.0'}, 'materials': [{'name': 'flat'}]}
        js = json.dumps(gltf_materials).encode()
        js += b' ' * (-len(js) % 4)
        data = b'\0\0\0\0'
        vrm.write_bytes(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + 4)
                        + struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', 4, b'BIN\0') + data)
        result = extract(vrm, self.root / 'flat_out')
        self.assertEqual(result['images'][0]['width'], 4)


if __name__ == '__main__':
    unittest.main()
