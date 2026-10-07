import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um.dragon_vrm_check import skin_warnings, _local, _mul


def _inverse(m):
    n = 4
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        d = a[c][c]
        a[c] = [v / d for v in a[c]]
        for r in range(n):
            if r != c:
                f = a[r][c]
                a[r] = [v - f * w for v, w in zip(a[r], a[c])]
    return [row[n:] for row in a]


def _glb(sheared_joint):
    """A root with two chained joints; the stored inverse bind matrices come from the true (Unity) world matrices."""
    nodes = [{'name': 'root', 'children': [1]},
             {'name': 'boneA', 'translation': [0, 1, 0], 'rotation': [0, 0, 0.7071068, 0.7071068], 'scale': [1.5, 1, 1],
              'children': [2]},
             {'name': 'boneB', 'translation': [0, 1, 0]}, {'name': 'mesh', 'skin': 0}]
    world = {}
    for i in (0, 1, 2):
        local = _local(nodes[i])
        parent = {1: 0, 2: 1}.get(i)
        world[i] = _mul(world[parent], local) if parent is not None else local
    true_world = {i: [row[:] for row in w] for i, w in world.items()}
    if sheared_joint:  # Unity world with a shear a TRS node cannot hold
        true_world[2][0][1] += 0.5
    ibm = [_inverse(true_world[i]) for i in (0, 1, 2)]
    floats = [ibm[k][r][c] for k in range(3) for c in range(4) for r in range(4)]  # column-major
    binary = struct.pack('<%df' % len(floats), *floats)
    gltf = {'asset': {'version': '2.0'}, 'nodes': nodes, 'skins': [{'joints': [0, 1, 2], 'inverseBindMatrices': 0}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'MAT4'}],
            'bufferViews': [{'buffer': 0, 'byteLength': len(binary)}], 'buffers': [{'byteLength': len(binary)}]}
    text = json.dumps(gltf).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(binary), 0x004E4942) + binary
    return b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body


class VrmSkinCheckTests(unittest.TestCase):
    def check(self, sheared):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.vrm'
            path.write_bytes(_glb(sheared))
            return skin_warnings(path)

    def test_consistent_bones_give_no_warning(self):
        self.assertEqual(self.check(False), [])

    def test_a_bone_whose_pose_differs_from_its_bind_pose_is_reported(self):
        warnings = self.check(True)
        self.assertEqual(len(warnings), 1)
        self.assertIn('boneB', warnings[0])
        self.assertIn('non-uniform scale: boneA', warnings[0])

    def test_broken_or_missing_files_never_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / 'bad.vrm'
            bad.write_bytes(b'not a glb')
            self.assertEqual(skin_warnings(bad), [])
            self.assertEqual(skin_warnings(Path(folder) / 'missing.vrm'), [])


if __name__ == '__main__':
    unittest.main()
