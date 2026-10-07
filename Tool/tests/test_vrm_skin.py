import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import numpy as np
    from um.dragon_vrm_skin import VrmSkin, gltf_to_blender
except ImportError:  # numpy ships with Blender, not necessarily with the system Python
    np = None


def _pad(data, fill=b'\0'):
    return data + fill * (-len(data) % 4)


def _glb(joint_y=2.0):
    """root -> boneA (bind y=1, posed at joint_y) ; one skinned mesh node and one plain mesh node under boneA."""
    positions = [(0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    joints = [(0, 0, 0, 0), (0, 0, 0, 0)]  # index into the skin's joint list (its only joint is node 1)
    weights = [(1.0, 0, 0, 0), (1.0, 0, 0, 0)]
    # joints: node 1 (boneA). inverse bind = translate(0,-1,0), stored column-major
    ibm = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1]
    blobs = [struct.pack('<6f', *[c for p in positions for c in p]),
             _pad(struct.pack('<8B', *[c for j in joints for c in j])),
             struct.pack('<8f', *[c for w in weights for c in w]),
             struct.pack('<16f', *ibm)]
    offsets, binary = [], b''
    for blob in blobs:
        offsets.append(len(binary))
        binary += blob
    nodes = [{'name': 'root', 'children': [1, 3]},
             {'name': 'boneA', 'translation': [0, joint_y, 0], 'children': [2]},
             {'name': 'skinned', 'mesh': 0, 'skin': 0},
             {'name': 'plain', 'mesh': 1, 'translation': [0, 0, 5]}]
    gltf = {'asset': {'version': '2.0'}, 'nodes': nodes,
            'skins': [{'joints': [1], 'inverseBindMatrices': 3}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'JOINTS_0': 1, 'WEIGHTS_0': 2}}]},
                       {'primitives': [{'attributes': {'POSITION': 0}}]}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                          {'bufferView': 1, 'componentType': 5121, 'count': 2, 'type': 'VEC4'},
                          {'bufferView': 2, 'componentType': 5126, 'count': 2, 'type': 'VEC4'},
                          {'bufferView': 3, 'componentType': 5126, 'count': 1, 'type': 'MAT4'}],
            'bufferViews': [{'buffer': 0, 'byteOffset': o, 'byteLength': len(b)} for o, b in zip(offsets, blobs)],
            'buffers': [{'byteLength': len(binary)}]}
    text = _pad(json.dumps(gltf).encode(), b' ')
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(binary), 0x004E4942) + binary
    return b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body


@unittest.skipIf(np is None, 'needs numpy')
class VrmSkinTests(unittest.TestCase):
    def load(self, joint_y=2.0):
        folder = tempfile.mkdtemp()
        path = Path(folder) / 'a.vrm'
        path.write_bytes(_glb(joint_y))
        return VrmSkin(path)

    def test_a_skinned_vertex_follows_its_bone_by_the_amount_the_bone_moved(self):
        skin = self.load(joint_y=2.0)  # bound at y=1, posed at y=2: everything moves up by one
        positions, joints, weights = skin.final_positions(2)
        np.testing.assert_allclose(positions, [(0, 2, 0), (1, 2, 0)], atol=1e-6)
        self.assertEqual(int(joints[0][0]), 1)  # reported as glTF node indices
        self.assertAlmostEqual(float(weights[0][0]), 1.0)

    def test_a_bone_at_its_bind_pose_leaves_the_mesh_where_it_is(self):
        skin = self.load(joint_y=1.0)
        positions, *_ = skin.final_positions(2)
        np.testing.assert_allclose(positions, [(0, 1, 0), (1, 1, 0)], atol=1e-6)

    def test_a_plain_mesh_uses_its_node_matrix_and_has_no_skin_data(self):
        skin = self.load()
        positions, joints, weights = skin.final_positions(3)
        np.testing.assert_allclose(positions, [(0, 1, 5), (1, 1, 5)], atol=1e-6)
        self.assertIsNone(joints)
        self.assertIsNone(weights)

    def test_ancestor_lookup_finds_the_nearest_bone_of_the_main_rig(self):
        skin = self.load()
        self.assertEqual(skin.ancestor_in(2, {'root'}), 'root')
        self.assertEqual(skin.ancestor_in(2, {'boneA', 'root'}), 'boneA')
        self.assertIsNone(skin.ancestor_in(2, {'missing'}))

    def test_glTF_to_blender_axes(self):
        out = gltf_to_blender(np.array([[1.0, 2.0, 3.0]]))
        np.testing.assert_allclose(out, [[1.0, -3.0, 2.0]])


if __name__ == '__main__':
    unittest.main()
