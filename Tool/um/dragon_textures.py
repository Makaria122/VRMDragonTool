"""Extract local VRM glTF base-color images to private DXT5 DDS files.

This is a material *source* stage, not a Dragon Engine shader or MOD export.
No external URI/network files are read; output directory must not exist.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import struct
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_CHUNK = 64 * 1024 * 1024
MAX_SOURCE_SIDE = 8192   # larger source images are refused (memory); up to this size they are accepted
MAX_OUTPUT_SIDE = 4096   # DDS textures are written at most this large
IMAGE_MIMES = ('image/png', 'image/jpeg', 'image/webp')
IMAGE_FORMATS = ('PNG', 'JPEG', 'WEBP')
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_SIDE * MAX_SOURCE_SIDE


class TextureError(ValueError):
    pass


def fit_for_dxt(image):
    """Scale to at most MAX_OUTPUT_SIDE and round each side up to a multiple of 4 (DXT blocks).

    Resampling keeps the 0..1 UV mapping valid, padding would not.
    """
    width, height = image.size
    scale = min(1.0, MAX_OUTPUT_SIDE / max(width, height))
    new_width = -(-max(4, round(width * scale)) // 4) * 4
    new_height = -(-max(4, round(height * scale)) // 4) * 4
    if (new_width, new_height) == (width, height):
        return image
    return image.resize((new_width, new_height), Image.LANCZOS)


def _glb(path):
    with path.open('rb') as f:
        header = f.read(12)
        if len(header) != 12 or header[:4] != b'glTF':
            raise TextureError('Not a GLB/VRM')
        version, size = struct.unpack('<II', header[4:])
        if version != 2 or size != path.stat().st_size:
            raise TextureError('Unsupported GLB version or file length')
        length, kind = struct.unpack('<I4s', f.read(8))
        if kind != b'JSON' or not 0 < length <= MAX_CHUNK:
            raise TextureError('Invalid GLB JSON')
        gltf = json.loads(f.read(length).decode('utf-8'))
        bin_header = f.read(8)
        if len(bin_header) != 8:
            raise TextureError('Missing GLB binary chunk')
        bin_length, bin_kind = struct.unpack('<I4s', bin_header)
        bin_start = f.tell()
        if bin_kind != b'BIN\0' or bin_start + bin_length != size:
            raise TextureError('Invalid GLB binary chunk')
    return gltf, bin_start, bin_length


def texture_namespace(vrm: Path, target_id: str = 'avatar') -> str:
    # Short ASCII stems fit the GMD texture-name field. Never use avatar filenames
    # as identity: different contents with the same name must remain isolated.
    from um.dragon_targets import target_ids, get_target
    if '__' in target_id:
        get_target(target_id)  # reject unknown/unregistered variants
        target_id = target_id.split('__', 1)[0]
    if target_id != 'avatar' and target_id not in target_ids():
        raise TextureError('Unsupported texture namespace target')
    if target_id.startswith('custom_'):
        # Distinct short code per custom target so two custom targets never share DDS names.
        code = 'u' + hashlib.sha256(target_id.encode()).hexdigest()[:3]
        digest = hashlib.sha256()
        with vrm.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return f'v_{code}_{digest.hexdigest()[:16]}'
    # Distinct short codes: initials alone collide for Sugiura/Saori/Soma/Sawa.
    code = {'avatar':'a', 'yagami':'y', 'kaito':'k', 'sugiura':'sg',
            'tsukumo':'tk', 'saori':'sr', 'higashi':'hg', 'tesso':'ts',
            'kuwana':'kw', 'soma':'so', 'akutsu':'ak', 'genda':'gn',
            'hoshino':'hs', 'mafuyu':'mf', 'sawa':'sw'}[target_id]
    digest = hashlib.sha256()
    with vrm.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return f'v_{code}_{digest.hexdigest()[:16]}'


def extract(vrm: str | Path, output: str | Path, target_id: str = 'avatar') -> dict:
    vrm = Path(vrm).expanduser().resolve(strict=True)
    output = Path(output).expanduser().resolve()
    if output.exists() or not output.parent.is_dir():
        raise TextureError('Select a NEW private output directory in an existing folder')
    # Refuse writing into the game, tool or repository when called as a bundled GUI.
    names = {p.lower() for p in output.parts}
    program_root = Path(__file__).resolve().parents[1]
    bundle_root = (program_root.parent if (program_root.parent / 'Blender' / 'blender.exe').is_file()
                   else program_root)
    from um.dragon_beta import portable_data_path
    if ({'steamapps', 'common'} <= names or 'mods' in names
            or (output.is_relative_to(bundle_root) and not portable_data_path(output,bundle_root))):
        raise TextureError('Output must be outside game and tool directories')
    namespace = texture_namespace(vrm, target_id)
    gltf, start, size = _glb(vrm)
    textures = gltf.get('textures', [])
    images = gltf.get('images', [])
    views = gltf.get('bufferViews', [])
    materials = gltf.get('materials', [])
    if not all(isinstance(v, list) for v in (textures, images, views, materials)):
        raise TextureError('Invalid glTF image/material tables')
    targets = {}
    flat_files = []
    material_map = []
    for index, mat in enumerate(materials):
        if not isinstance(mat, dict):
            raise TextureError('Invalid material')
        ref = mat.get('pbrMetallicRoughness', {}).get('baseColorTexture', {})
        tid = ref.get('index') if isinstance(ref, dict) else None
        entry = {'material_index': index, 'material_name': mat.get('name', f'material_{index}'),
                 'image_index': None, 'dds': None}
        if tid is not None:
            if type(tid) is not int or not 0 <= tid < len(textures):
                raise TextureError(f'Invalid material texture index: {index}')
            texture = textures[tid]
            image_id = texture.get('source') if isinstance(texture, dict) else None
            if type(image_id) is not int or not 0 <= image_id < len(images):
                raise TextureError(f'Invalid embedded image reference: {index}')
            entry['image_index'] = image_id
            entry['dds'] = f'{namespace}_d{image_id:02}.dds'
            targets[image_id] = entry['dds']
        if entry['dds'] is None:
            factor = mat.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
            if (not isinstance(factor, list) or len(factor) != 4
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in factor)):
                raise TextureError(f'Invalid flat-color material: {index}')
            entry['dds'] = f'{namespace}_f{index:02}.dds'
            flat_files.append((index, entry['dds'], tuple(round(255 * v) for v in factor)))
        material_map.append(entry)
    if not targets and not flat_files:
        raise TextureError('No glTF materials to export')
    output.mkdir()  # create only after validation; never overwrite existing assets
    written = []
    with vrm.open('rb') as f:
        for image_id, filename in sorted(targets.items()):
            image = images[image_id]
            if not isinstance(image, dict) or image.get('mimeType') not in IMAGE_MIMES:
                raise TextureError(f'Only embedded PNG/JPEG/WebP images are supported: {image_id}')
            view_id = image.get('bufferView')
            if type(view_id) is not int or not 0 <= view_id < len(views):
                raise TextureError(f'Image is not embedded in GLB: {image_id}')
            view = views[view_id]
            offset, length = view.get('byteOffset', 0), view.get('byteLength')
            if (type(offset) is not int or type(length) is not int or offset < 0
                    or not 0 < length <= MAX_CHUNK or offset + length > size):
                raise TextureError(f'Image buffer view out of bounds: {image_id}')
            f.seek(start + offset)
            blob = f.read(length)
            try:
                with Image.open(io.BytesIO(blob)) as source:
                    if source.format not in IMAGE_FORMATS or max(source.size) > MAX_SOURCE_SIDE:
                        raise TextureError(f'Unsupported image format/size: {image_id}')
                    source.load()
                    rgba = source.convert('RGBA')
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise TextureError(f'Invalid embedded image: {image_id}') from exc
            original_size = rgba.size
            rgba = fit_for_dxt(rgba)
            dest = output / filename
            with dest.open('xb') as target:
                rgba.save(target, format='DDS', pixel_format='DXT5')
            with Image.open(dest) as check:
                if check.size != rgba.size:
                    raise TextureError(f'DDS dimension mismatch: {image_id}')
            entry_out = {'image_index': image_id, 'filename': filename,
                         'width': rgba.width, 'height': rgba.height,
                         'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
            if original_size != rgba.size:
                entry_out['resized_from'] = list(original_size)
            written.append(entry_out)
    for index, filename, rgba in flat_files:
        dest = output / filename
        with dest.open('xb') as target:
            Image.new('RGBA', (4, 4), rgba).save(target, format='DDS', pixel_format='DXT5')
        written.append({'image_index': None, 'material_index': index, 'filename': filename,
                        'width': 4, 'height': 4, 'flat_base_color': list(rgba),
                        'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
    result = {'schema_version': 2, 'texture_namespace': namespace, 'target_id': target_id,
              'source_vrm': str(vrm), 'private_output': str(output),
              'dds_format': 'DXT5', 'images': written, 'materials': material_map,
              'gmd_materials_created': False, 'game_ready': False}
    with (output / 'texture-map.json').open('x', encoding='utf-8') as manifest:
        json.dump(result, manifest, ensure_ascii=False, indent=2)
        manifest.write('\n')
    return result
