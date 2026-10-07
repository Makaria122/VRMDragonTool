"""Final vertex positions of a VRM computed the way the glTF specification defines them.

Blender's glTF importer does not reproduce every VRM exactly (some bones are posed with a 90 degree rotation and a huge
offset, which stretched a face down to the chest). The numbers in the file are authoritative: a skinned vertex ends up at
sum(weight * jointWorld * inverseBind * position), a plain mesh at nodeWorld * position. This module reads the VRM
itself and returns those positions (in glTF world space) per mesh node, so the preview can use them instead of
Blender's guess. It needs numpy (Blender ships it) and has no Blender dependency, so it can be tested without Blender.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

COMPONENT_TYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class VrmSkin:
    def __init__(self, path):
        data = Path(path).read_bytes()
        if data[:4] != b'glTF':
            raise ValueError('not a GLB/VRM file')
        length = struct.unpack('<I', data[12:16])[0]
        self.gltf = json.loads(data[20:20 + length])
        self.binary = data[20 + length + 8:]
        self.nodes = self.gltf.get('nodes', [])
        self.parent = {c: i for i, n in enumerate(self.nodes) for c in n.get('children', [])}
        self._world: dict[int, np.ndarray] = {}

    # ---- node matrices ----------------------------------------------------------------------------
    def local(self, index) -> np.ndarray:
        node = self.nodes[index]
        if 'matrix' in node:
            return np.array(node['matrix'], dtype=float).reshape(4, 4).T
        x, y, z, w = node.get('rotation', (0, 0, 0, 1))
        sx, sy, sz = node.get('scale', (1, 1, 1))
        rot = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        out = np.eye(4)
        out[:3, :3] = rot * np.array([sx, sy, sz])
        out[:3, 3] = node.get('translation', (0, 0, 0))
        return out

    def world(self, index) -> np.ndarray:
        if index not in self._world:
            local = self.local(index)
            self._world[index] = self.world(self.parent[index]) @ local if index in self.parent else local
        return self._world[index]

    def name(self, index) -> str:
        return self.nodes[index].get('name', f'node{index}')

    def ancestor_in(self, index, names: set[str]) -> str | None:
        """Nearest node (starting at `index` itself) whose name is in `names`."""
        while index is not None:
            if self.name(index) in names:
                return self.name(index)
            index = self.parent.get(index)
        return None

    # ---- accessors --------------------------------------------------------------------------------
    def read(self, accessor_index) -> np.ndarray:
        accessor = self.gltf['accessors'][accessor_index]
        view = self.gltf['bufferViews'][accessor['bufferView']]
        dtype = np.dtype(COMPONENT_TYPES[accessor['componentType']])
        width = COMPONENTS[accessor['type']]
        count = accessor['count']
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        stride = view.get('byteStride') or dtype.itemsize * width
        raw = np.ndarray((count, width), dtype=dtype, buffer=self.binary, offset=offset,
                         strides=(stride, dtype.itemsize)).copy()
        if accessor.get('normalized'):
            raw = raw.astype(np.float32) / float(np.iinfo(dtype).max) if dtype.kind in 'ui' else raw
        return raw

    # ---- results ----------------------------------------------------------------------------------
    def mesh_nodes(self):
        return [i for i, n in enumerate(self.nodes) if 'mesh' in n]

    def skin_matrices(self, skin_index) -> tuple[list[int], np.ndarray]:
        skin = self.gltf['skins'][skin_index]
        joints = skin['joints']
        ibm_accessor = skin.get('inverseBindMatrices')
        if ibm_accessor is None:
            ibm = np.tile(np.eye(4), (len(joints), 1, 1))
        else:
            ibm = self.read(ibm_accessor).reshape(-1, 4, 4).astype(float).transpose(0, 2, 1)  # column-major in the file
        return joints, np.array([self.world(j) @ ibm[k] for k, j in enumerate(joints)])

    def final_positions(self, node_index):
        """(positions in glTF world space [N,3], skin joint node indices per vertex [N,4] or None, weights [N,4] or None).

        Vertices of all primitives are concatenated in primitive order, the same order Blender's importer uses.
        """
        node = self.nodes[node_index]
        mesh = self.gltf['meshes'][node['mesh']]
        skin_index = node.get('skin')
        if skin_index is not None:
            joints, matrices = self.skin_matrices(skin_index)
        out, joint_ids, weights = [], [], []
        for primitive in mesh['primitives']:
            positions = self.read(primitive['attributes']['POSITION']).astype(float)
            homogeneous = np.hstack([positions, np.ones((len(positions), 1))])
            if skin_index is not None and 'JOINTS_0' in primitive['attributes']:
                j = self.read(primitive['attributes']['JOINTS_0']).astype(int)
                w = self.read(primitive['attributes']['WEIGHTS_0']).astype(float)
                total = w.sum(axis=1, keepdims=True)
                w = np.divide(w, total, out=np.zeros_like(w), where=total > 1e-12)
                result = np.zeros((len(positions), 3))
                for k in range(4):
                    result += w[:, k:k + 1] * np.einsum('nij,nj->ni', matrices[j[:, k]], homogeneous)[:, :3]
                out.append(result)
                joint_ids.append(np.array(joints)[j])
                weights.append(w)
            else:
                out.append((self.world(node_index) @ homogeneous.T).T[:, :3])
        if skin_index is not None and joint_ids:
            return np.vstack(out), np.vstack(joint_ids), np.vstack(weights)
        return np.vstack(out), None, None


def gltf_to_blender(points: np.ndarray) -> np.ndarray:
    """glTF is Y-up, Blender Z-up: (x, y, z) -> (x, -z, y)."""
    return np.stack([points[:, 0], -points[:, 2], points[:, 1]], axis=1)
