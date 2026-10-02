"""Explicit four-slot dummy-map recipe; no bpy dependency for synthetic tests."""
from pathlib import Path

DUMMY_SLOTS = ('texture_multi', 'texture_normal', 'texture_rt', 'texture_rd')


def select_material_template(candidates, region):
    """Select an existing native template without inventing a shader name.

    Eye shaders must not be used as a generic avatar template. Region labels are
    proposals from the recorded profile, not proof of material/alpha compatibility.
    """
    safe = [(name, material) for name, material in candidates
            if not any(tag in name.lower() for tag in ('[eye]', '[mouth]'))]
    if region == 'hair':
        preferred = [(name, mat) for name, mat in safe if '[hair]' in name.lower()]
    elif region == 'face':
        preferred = [(name, mat) for name, mat in safe
                     if name.lower().startswith('sd_o') and '[skin]' in name.lower()]
    else:
        # sd_d1dzt came from eyeline/eyeshadow decals, not opaque clothing.
        # Copying it also copies its special attribute flags even at opacity 255.
        preferred = [(name, mat) for name, mat in safe
                     if name.lower().startswith('sd_o')
                     and '[hair]' not in name.lower() and '[skin]' not in name.lower()]
    if not preferred:
        preferred = [(name, mat) for name, mat in safe
                     if name.lower().startswith('sd_o') and '[hair]' not in name.lower()]
    if not preferred:
        raise RuntimeError(f'No non-eye material template for source region {region}')
    return preferred[0]


def apply_matte_specular(shader):
    socket = shader.inputs.get('Specular color')
    if socket is None:
        raise RuntimeError('Target shader lacks Specular color input')
    socket.default_value = (0.0, 0.0, 0.0, 1.0)


def apply_dummy_maps(material, shader, slots, directory, load_image):
    """Give every auxiliary slot its own image node, even if initially unlinked.

    Diffuse and shader parameters remain untouched. A missing recipe is an error,
    rather than a silent fallback to native maps. Inputs are user-owned DDS files.
    """
    if set(slots) != set(DUMMY_SLOTS):
        raise RuntimeError('All four dummy texture slots are required: multi, normal, rt, rd')
    prepared = {}
    for slot in DUMMY_SLOTS:
        filename = slots[slot]
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith('.dds'):
            raise RuntimeError(f'Invalid dummy DDS filename: {slot}')
        socket = shader.inputs.get(slot)
        if socket is None:
            raise RuntimeError(f'Target shader has no dummy texture socket: {slot}')
        path = Path(directory) / filename
        with path.open('rb') as stream:
            if stream.read(4) != b'DDS ':
                raise RuntimeError(f'Invalid private dummy DDS: {path}')
        prepared[slot] = (socket, path)
    assigned = {}
    for slot, (socket, path) in prepared.items():
        for link in list(socket.links):
            material.node_tree.links.remove(link)
        node = material.node_tree.nodes.new('ShaderNodeTexImage')
        node.label = f'Explicit dummy {slot}'
        node.image = load_image(str(path), check_existing=True)
        material.node_tree.links.new(node.outputs['Color'], socket)
        assigned[slot] = path.stem
    return assigned


def verify_dummy_references(attributes, slots):
    """Verify *active* exported material attributes, not stale texture-table entries."""
    if set(slots) != set(DUMMY_SLOTS):
        raise RuntimeError('Incomplete dummy-map recipe')
    expected = {key: Path(value).stem for key, value in slots.items()}
    count = 0
    for attribute in attributes:
        count += 1
        for slot, name in expected.items():
            actual = getattr(attribute, slot)
            if actual != name:
                raise RuntimeError(f'Exported dummy-map mismatch: {slot}: {actual!r} != {name!r}')
    if not count:
        raise RuntimeError('No exported materials to verify')
    return count
