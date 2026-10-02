"""Game-independent neutral DDS: BC1 multi/white, BGRA8 normal (legacy layout)."""
from __future__ import annotations
import struct
from pathlib import Path

RECIPES = {
    'multi': (49, 255, 49, 255),
    'normal': (128, 128, 255, 255),
    'white': (255, 255, 255, 255),
}
POLICY = 'neutral-bc1-bgra-v2'


def dds_bytes(rgba: tuple[int, int, int, int], size: int = 4, *,
              encoding: str = 'bgra', mipmaps: int = 1) -> bytes:
    if len(rgba) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in rgba):
        raise ValueError('RGBA recipe must contain four byte values')
    if size != 4 or mipmaps not in (1, 3):
        raise ValueError('Neutral maps require 4x4 and one or three mip levels')
    caps = 0x1000 | (0x400008 if mipmaps > 1 else 0)
    mip_count = mipmaps if mipmaps > 1 else 0
    if encoding == 'bc1':
        if rgba[3] != 255:
            raise ValueError('Neutral BC1 maps must be opaque')
        # Encode our constant recipe, not any bytes from a game DDS.
        r,g,b,_ = rgba
        rgb565 = ((r*31+127)//255 << 11) | ((g*63+127)//255 << 5) | ((b*31+127)//255)
        # Both endpoints match; index zero is opaque even in BC1 three-color mode.
        block = struct.pack('<HHI',rgb565,rgb565,0)
        payload = block*mipmaps  # 4x4, 2x2 and 1x1 each occupy one BC1 block
        pf = struct.pack('<8I',32,0x4,int.from_bytes(b'DXT1','little'),0,0,0,0,0)
        flags,pitch = 0x81007,8  # DDSD_LINEARSIZE, base-level block bytes
    elif encoding == 'bgra':
        if mipmaps != 1:
            raise ValueError('Neutral normal map uses one BGRA8 level')
        pf = struct.pack('<8I',32,0x41,0,32,0x00ff0000,0x0000ff00,0x000000ff,0xff000000)
        payload = bytes((rgba[2],rgba[1],rgba[0],rgba[3]))*(size*size)
        flags,pitch = 0x100f,size*4
    else:
        raise ValueError('Unsupported neutral DDS encoding')
    if mipmaps > 1:flags |= 0x20000
    header = struct.pack('<7I',124,flags,size,size,pitch,0,mip_count) + bytes(44) + pf + struct.pack('<5I',caps,0,0,0,0)
    return b'DDS '+header+payload


def write_neutral_maps(directory: str | Path) -> dict[str, Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    result = {}
    for name,rgba in RECIPES.items():
        path = root / ('dummy_nmap.dds' if name=='normal' else f'dummy_{name}.dds')
        path.write_bytes(dds_bytes(rgba,encoding='bgra' if name=='normal' else 'bc1',
                                  mipmaps=3 if name=='multi' else 1))
        result[name] = path
    return result
