"""Procedurally generated, game-independent neutral 4x4 DDS maps."""
from __future__ import annotations
import struct
from pathlib import Path

RECIPES = {
    'multi': (49, 255, 49, 255),
    'normal': (128, 128, 255, 255),
    'white': (255, 255, 255, 255),
}

def dds_bytes(rgba: tuple[int, int, int, int], size: int = 4) -> bytes:
    if len(rgba) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in rgba):
        raise ValueError('RGBA recipe must contain four byte values')
    if size != 4:
        raise ValueError('Neutral DDS maps are fixed at 4x4')
    # DDS_HEADER (124 bytes), uncompressed 32-bit RGBA pixel format.
    pf = struct.pack('<8I', 32, 0x41, 0, 32,
                     0x000000ff, 0x0000ff00, 0x00ff0000, 0xff000000)
    header = struct.pack('<7I', 124, 0x100f, size, size,
                         size * 4, 0, 0) + bytes(44) + pf + struct.pack('<5I',0x1000,0,0,0,0)
    pixel = bytes((rgba[0], rgba[1], rgba[2], rgba[3]))
    return b'DDS ' + header + pixel * (size * size)

def write_neutral_maps(directory: str | Path) -> dict[str, Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, rgba in RECIPES.items():
        path = root / ('dummy_nmap.dds' if name=='normal' else f'dummy_{name}.dds')
        path.write_bytes(dds_bytes(rgba))
        result[name] = path
    return result
