"""Pre-check of a VRM/GLB for bones whose skin pose cannot be represented, without Blender.

glTF stores each node as translation/rotation/scale. A bone with a non-uniform scale that is also rotated relative
to its parent has a world matrix with shear in Unity, which that format cannot keep: viewers (and this tool) then
pose the bone and its children differently from Unity, and parts weighted to them look deformed (a hair lock
sticking out). The skin matrix of every joint, world matrix x inverse bind matrix, must be the same for all
joints of a skin; joints that differ are reported.
"""
from __future__ import annotations

import json
import struct
from collections import Counter
from pathlib import Path

TOLERANCE_M = 0.01  # matrix entries differing by more than this are reported (about a centimetre)


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _local(node):
    if 'matrix' in node:
        m = node['matrix']
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get('translation', (0, 0, 0))
    x, y, z, w = node.get('rotation', (0, 0, 0, 1))
    sx, sy, sz = node.get('scale', (1, 1, 1))
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0, 0, 0, 1]]


def _read_glb(path):
    data = Path(path).read_bytes()
    if data[:4] != b'glTF':
        raise ValueError('not a GLB/VRM file')
    length = struct.unpack('<I', data[12:16])[0]
    gltf = json.loads(data[20:20 + length])
    binary = data[20 + length + 8:]
    return gltf, binary


def skin_warnings(path, limit: int = 8) -> list[str]:
    """Human-readable warnings; an empty list means nothing suspicious. Never raises for a broken file."""
    try:
        gltf, binary = _read_glb(path)
        nodes = gltf.get('nodes', [])
        parent = {c: i for i, n in enumerate(nodes) for c in n.get('children', [])}
        cache: dict[int, list] = {}

        def world(i):
            if i not in cache:
                local = _local(nodes[i])
                cache[i] = _mul(world(parent[i]), local) if i in parent else local
            return cache[i]

        owners = {n['skin']: n.get('name', '?') for n in nodes if 'skin' in n}
        found: dict[tuple, list] = {}  # the same bones are often shared by several skins (hair meshes)
        for index, skin in enumerate(gltf.get('skins', [])):
            ibm_index = skin.get('inverseBindMatrices')
            joints = skin.get('joints', [])
            if ibm_index is None or not joints:
                continue
            accessor = gltf['accessors'][ibm_index]
            view = gltf['bufferViews'][accessor['bufferView']]
            offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
            floats = struct.unpack_from('<%df' % (16 * accessor['count']), binary, offset)
            matrices = []
            for k, joint in enumerate(joints):
                flat = floats[16 * k:16 * k + 16]
                ibm = [[flat[c * 4 + r] for c in range(4)] for r in range(4)]
                matrices.append(_mul(world(joint), ibm))
            keys = [tuple(round(v, 3) for row in m for v in row) for m in matrices]
            reference = matrices[keys.index(Counter(keys).most_common(1)[0][0])]
            bad = []
            for joint, m in zip(joints, matrices):
                deviation = max(abs(m[i][j] - reference[i][j]) for i in range(4) for j in range(4))
                if deviation > TOLERANCE_M:
                    bad.append((deviation, nodes[joint].get('name', '?')))
            if bad:
                bad.sort(reverse=True)
                entry = found.setdefault(tuple(sorted(name for _, name in bad)), [bad[0][0], [], bad, []])
                entry[1].append(str(owners.get(index, index)))
                for j in joints:
                    s = nodes[j].get('scale', (1, 1, 1))
                    if max(s) - min(s) > 0.05 and nodes[j].get('name', '?') not in entry[3]:
                        entry[3].append(nodes[j].get('name', '?'))
        warnings = []
        for deviation, meshes, bad, scaled in list(found.values())[:limit]:
            names = ', '.join(name for _, name in bad[:5]) + (' ...' if len(bad) > 5 else '')
            hint = f' Bones with a non-uniform scale: {", ".join(scaled[:4])}.' if scaled else ''
            warnings.append(f'The pose of {len(bad)} bone(s) ({names}) used by {", ".join(meshes[:4])} differs from the '
                            f'stored bind pose by up to {deviation * 100:.1f} cm; parts weighted to them can look deformed '
                            f'(for example a hair lock sticking out).{hint} Reset the scale of these bones to 1 in the '
                            f'avatar tool (for example Unity) and export again.')
        return warnings
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return []
