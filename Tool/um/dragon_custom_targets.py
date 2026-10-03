"""User-defined ("Other") targets: GMD files from any Dragon Engine game, registered from the GUI.

Two ways to register:
* a single character from a few GMD files (tops, optional face/hair), or
* a whole character: search a folder for every GMD whose name contains the character's name, inspect them all,
  and register one base set plus all compatible extra parts (other outfits, hair styles, faces) so that one
  conversion replaces every part of the character.

The files are inspected read-only in Blender, checked for the skeleton the fitting code needs, and copied once
into Tool/userdata/targets/<id>/ so that the conversion never touches the game folder. The definition is stored
as JSON and shows up in the target list.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path

PREFIX = 'custom_'
SCHEMA = 2
SUPPORTED_SCHEMAS = (1, 2)
ROLES = ('tops', 'face', 'hair')
STEM_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$')
NAME_PATTERN = re.compile(r'^[a-z0-9_]{2,40}$')
FINGER_WORDS = ('Thumb', 'Index', 'Middle', 'Ring', 'Little')
MAX_PARTS = 400


class CustomTargetError(ValueError):
    pass


def bundle_root() -> Path:
    return Path(__file__).resolve().parents[2]


def custom_dir() -> Path:
    return bundle_root() / 'Tool' / 'userdata' / 'targets'


def sanitize_id(name: str) -> str:
    """'c_cm_x_ichiban' -> 'custom_c_cm_x_ichiban'; never contains '__' (reserved for variants)."""
    core = re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')
    core = re.sub(r'_+', '_', core)[:40].strip('_')
    if not core:
        raise CustomTargetError('The target needs a name made of letters or digits')
    return PREFIX + core


def required_target_bones():
    """Target bone names the fitting code cannot work without (fingers are optional)."""
    from um.dragon_fit import BONE_MAP
    return {role: bone for role, bone in BONE_MAP.items() if not any(word in role for word in FINGER_WORDS)}


def find_siblings(tops_path) -> dict:
    """Find face/hair GMDs next to a tops GMD laid out as <root>/tops/<id>/<id>.gmd (the Dragon Engine layout)."""
    tops = Path(tops_path)
    stem = tops.stem
    found = {}
    try:
        root = tops.parents[2]
    except IndexError:
        return found
    if tops.parent.parent.name.lower() != 'tops':
        return found
    for role, letter in (('face', 'f'), ('hair', 'h')):
        if '_x_' not in stem:
            continue
        sibling = stem.replace('_x_', f'_{letter}_', 1)
        candidate = root / role / sibling / f'{sibling}.gmd'
        if candidate.is_file():
            found[role] = candidate
    return found


# ---- whole-character search -----------------------------------------------------------------------------
SPECIAL_RULES = (
    (re.compile(r'naked|nude|nkd'), 'undressed model'),
    (re.compile(r'swim'), 'swimwear'),
    (re.compile(r'dead|corpse'), 'dead state'),
    (re.compile(r'(^|_)age\d+|(^|_)chd(_|$)|child|young|(^|_)boy(_|$)'), 'different age'),
    (re.compile(r'test|dummy|debug'), 'test model'),
    (re.compile(r'(^|_)sit(_|$)|chair|agura|sleep|lying|kneel'), 'special pose'),
)


def special_flags(stem: str) -> list[str]:
    """Names that suggest a model the VRM should not simply replace (unticked by default)."""
    lowered = stem.lower()
    return [reason for pattern, reason in SPECIAL_RULES if pattern.search(lowered)]


def role_of(path: Path) -> str:
    """tops/face/hair from the folder (<root>/tops/<id>/<id>.gmd) or from a _x_/_f_/_h_ marker in the name."""
    folder = path.parent.parent.name.lower()
    if folder in ROLES:
        return folder
    stem = path.stem.lower()
    for role, marker in (('tops', '_x_'), ('face', '_f_'), ('hair', '_h_')):
        if marker in stem:
            return role
    return 'other'


def _is_link(path: Path) -> bool:
    """Symlink or Windows junction/reparse point (os.walk does not treat junctions as links)."""
    try:
        info = os.lstat(path)
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def scan_character(root, name: str, limit: int = MAX_PARTS) -> list[dict]:
    """Every .gmd under root whose file name contains `name` (case-insensitive). Never follows links."""
    needle = str(name).strip().lower()
    if not NAME_PATTERN.match(needle):
        raise CustomTargetError('Type the character name with letters, digits or _ only (2 to 40 characters)')
    root = Path(root)
    if not root.is_dir():
        raise CustomTargetError('Choose an existing folder')
    found, seen = [], set()
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not _is_link(Path(current) / d))
        for file in sorted(files):
            path = Path(current) / file
            if path.suffix.lower() != '.gmd' or needle not in path.stem.lower() or _is_link(path):
                continue
            if path.stem in seen or not STEM_PATTERN.match(path.stem):
                continue
            seen.add(path.stem)
            found.append({'path': path, 'stem': path.stem, 'role': role_of(path), 'flags': special_flags(path.stem)})
            if len(found) > limit:
                raise CustomTargetError(f'More than {limit} files match "{needle}"; use a more specific name')
    order = {'tops': 0, 'face': 1, 'hair': 2, 'other': 3}
    return sorted(found, key=lambda c: (order[c['role']], c['stem']))


# ---- inspection (Blender, read-only) -------------------------------------------------------------------
def inspect_paths(items, blender, addon, runner=None, timeout: int = 600, chunk: int = 40, progress=None) -> dict:
    """Parse GMDs with the GMD add-on in a background Blender. items: [(label, path)]; returns {resolved path: parsed}."""
    import subprocess
    from um.dragon_log import failure_summary, run_logged
    runner = runner or run_logged
    blender, addon = Path(blender), Path(addon)
    if not blender.is_file():
        raise CustomTargetError('Blender was not found; set it up first (Blender tab)')
    worker = Path(__file__).with_name('dragon_variant_worker.py')
    entries = []
    for label, path in items:
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != '.gmd':
            raise CustomTargetError(f'Not a .gmd file: {path}')
        entries.append({'absolute_path': str(path.resolve()), 'source_relative_path': path.name,
                        'model_id': path.stem, 'region': label})
    parsed_all = {}
    for start in range(0, len(entries), chunk):
        part = entries[start:start + chunk]
        if progress:
            progress(start, len(entries))
        with tempfile.TemporaryDirectory(prefix='custom_target_') as temp:
            job, out = Path(temp) / 'job.json', Path(temp) / 'parsed.json'
            job.write_text(json.dumps({'addon': str(addon), 'files': part, 'output': str(out)}), encoding='utf-8')
            command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '1',
                       '--python', str(worker), '--', str(job)]
            try:
                proc = runner(command, 'inspect custom GMDs', timeout)
            except subprocess.TimeoutExpired as exc:
                raise CustomTargetError('Blender took too long to read the GMD files') from exc
            if not out.is_file():
                raise CustomTargetError('Blender could not read the GMD files: '
                                        + failure_summary(getattr(proc, 'stdout', ''), getattr(proc, 'stderr', '')))
            for item in json.loads(out.read_text(encoding='utf-8')):
                parsed_all[item.get('absolute_path')] = item
    if progress:
        progress(len(entries), len(entries))
    return {str(Path(path).resolve()): parsed_all.get(str(Path(path).resolve()), {}) for _, path in items}


def inspect_files(files: dict, blender, addon, runner=None, timeout: int = 600) -> dict:
    """{role: parsed} for a few GMDs given by role."""
    result = inspect_paths([(role, path) for role, path in files.items()], blender, addon, runner, timeout)
    return {role: result.get(str(Path(path).resolve()), {}) for role, path in files.items()}


def skeleton_problem(parsed: dict, name: str) -> str | None:
    """Why this inspected GMD cannot be used, or None when its skeleton has the bones the tool needs."""
    if parsed.get('load_status') != 'loaded':
        why = parsed.get('error') or parsed.get('load_status') or 'no result'
        return f'{name} could not be read as a GMD: {str(why).splitlines()[0][:120] if str(why) else why}'
    names = set(parsed.get('bone_names') or [])
    missing = sorted(bone for bone in required_target_bones().values() if bone not in names)
    if missing:
        return (f'{name} does not have the bones this tool needs ({len(missing)} missing, for example '
                f'{", ".join(missing[:6])}). Its skeleton is named differently from the supported Dragon Engine one.')
    return None


def classify(candidates: list[dict], inspections: dict) -> list[dict]:
    """Add bone_count, ok and reason to every candidate (in place) from the inspection results."""
    for item in candidates:
        if item['role'] not in ROLES:
            item.update(bone_count=None, ok=False, reason='cannot tell whether this is a body, face or hair file')
            continue
        parsed = inspections.get(str(Path(item['path']).resolve()), {})
        item['bone_count'] = parsed.get('bone_count')
        problem = skeleton_problem(parsed, Path(item['path']).name)
        item['ok'] = problem is None
        item['reason'] = problem or ''
        if problem is None and item['role'] == 'tops' and parsed.get('foot_support') is False:
            item['ok'] = False
            item['reason'] = ('partial model without feet (for example hands only): the floor cannot be measured, '
                              'and it cannot replace a full body')
    return candidates


def suggest_base(candidates: list[dict]) -> dict:
    """The main body/face/hair set: shortest plain name per role, among usable files of the commonest skeleton size."""
    usable = [c for c in candidates if c['ok'] and not c['flags']]
    sizes = collections.Counter(c['bone_count'] for c in usable if c['role'] == 'tops')
    if not sizes:
        return {}
    size = sizes.most_common(1)[0][0]
    base = {}
    for role in ROLES:
        options = [c for c in usable if c['role'] == role and c['bone_count'] == size]
        if options:
            base[role] = min(options, key=lambda c: (len(c['stem']), c['stem']))
    return base


def default_selection(candidates: list[dict], base: dict) -> set:
    """Stems ticked by default: usable and not special; the base set is always part of the character."""
    chosen = {c['stem'] for c in candidates if c['ok'] and not c['flags']}
    return chosen | {c['stem'] for c in base.values()}


# ---- definition (pure, unit-tested) --------------------------------------------------------------------
def build_definition(files: dict, inspections: dict, label: str | None = None, target_id: str | None = None) -> dict:
    """Validate the inspections and describe the target. Raises CustomTargetError with a readable reason."""
    if 'tops' not in files:
        raise CustomTargetError('A tops GMD (the body) is required')
    unknown = set(files) - set(ROLES)
    if unknown:
        raise CustomTargetError(f'Unknown GMD roles: {sorted(unknown)}')
    from um.dragon_fit import BONE_MAP
    counts, warnings = {}, []
    for role in files:
        item = inspections.get(role) or {}
        name = Path(files[role]).name
        problem = skeleton_problem(item, name)
        if problem:
            raise CustomTargetError(problem)
        if not STEM_PATTERN.match(Path(files[role]).stem):
            raise CustomTargetError(f'Unsupported file name: {name} (use letters, digits, _ . - only)')
        names = set(item.get('bone_names') or [])
        optional = [bone for role_name, bone in BONE_MAP.items()
                    if bone not in names and any(word in role_name for word in FINGER_WORDS)]
        if optional:
            warnings.append(f'{name}: {len(optional)} finger bones are missing; fingers will not be fitted')
        counts[role] = item.get('bone_count')
        for text in item.get('warnings') or []:
            warnings.append(f'{name}: {text}')
    if len(set(counts.values())) != 1 or not isinstance(counts['tops'], int) or counts['tops'] < 1:
        raise CustomTargetError(f'The GMDs must share one skeleton, but the bone counts differ: {counts}')
    stems = {role: Path(path).stem for role, path in files.items()}
    layout = '+'.join(role for role in ROLES if role in files)
    label = (label or '').strip() or f'Custom: {stems["tops"]}'
    return {'schema': SCHEMA, 'id': target_id or sanitize_id(stems['tops']), 'label': label[:60],
            'bone_count': counts['tops'], 'rig_prefix': stems['tops'], 'layout': layout, 'stems': stems,
            'parts': [], 'warnings': warnings, 'created': datetime.now().isoformat(timespec='seconds')}


def allowed_part_roles(layout: str) -> set:
    return {'tops': {'tops'}, 'tops+face': {'tops', 'face'}}.get(layout, set(ROLES))


def add_parts(definition: dict, selected: list[dict]) -> tuple[dict, list[dict]]:
    """Attach the chosen extra parts; returns (definition, skipped) where skipped explains each refusal."""
    allowed = allowed_part_roles(definition['layout'])
    base_stems = set(definition['stems'].values())
    parts, skipped = [], []
    for item in selected:
        if item['stem'] in base_stems:
            continue
        if not item.get('ok'):
            skipped.append({'stem': item['stem'], 'reason': item.get('reason') or 'not usable'})
        elif item['role'] not in allowed:
            skipped.append({'stem': item['stem'], 'reason': f"a {item['role']} file does not fit a {definition['layout']} character"})
        else:
            parts.append({'role': item['role'], 'stem': item['stem'], 'bone_count': item.get('bone_count'),
                          'flags': list(item.get('flags') or [])})
    order = {role: i for i, role in enumerate(ROLES)}
    definition = dict(definition, parts=sorted(parts, key=lambda p: (order[p['role']], p['stem'])))
    return definition, skipped


def _store_paths(definition: dict, directory: Path) -> dict:
    store = directory / definition['id']
    return {role: str(store / f'{stem}.gmd') for role, stem in definition['stems'].items()}


def to_target(definition: dict, directory=None):
    """Create the Target object for a stored definition (references are the private copies)."""
    from um.dragon_targets import ExportSlot, Target
    directory = Path(directory) if directory else custom_dir()
    stems = definition['stems']
    layout = definition['layout']
    target_id = definition['id']
    if not target_id.startswith(PREFIX) or '__' in target_id:
        raise CustomTargetError(f'Invalid custom target id: {target_id}')
    stored = _store_paths(definition, directory)
    tops = stems['tops']
    if layout == 'tops':
        slots = (ExportSlot('tops', 'tops', tops, ('tops', 'face', 'hair'), 'tops'),)
        roles = {'tops': tops, 'face': tops, 'hair': tops}
        refs = {'tops': stored['tops'], 'face': stored['tops'], 'hair': stored['tops']}
    elif layout == 'tops+face':
        slots = (ExportSlot('tops', 'tops', tops, ('tops',), 'tops'),
                 ExportSlot('face', 'face', stems['face'], ('face', 'hair'), 'face'))
        roles = {'tops': tops, 'face': stems['face'], 'hair': stems['face']}
        refs = {'tops': stored['tops'], 'face': stored['face'], 'hair': stored['face']}
    elif layout == 'tops+face+hair':
        slots = (ExportSlot('tops', 'tops', tops, ('tops',), 'tops'),
                 ExportSlot('face', 'face', stems['face'], ('face',), 'face'),
                 ExportSlot('hair', 'hair', stems['hair'], ('hair',), 'hair'))
        roles = dict(stems)
        refs = dict(stored)
    else:
        raise CustomTargetError(f'Unsupported layout: {layout}')
    note = ('Custom target from your own GMD files; compatibility with the game and in-game appearance are unverified. '
            + ' '.join(definition.get('warnings', [])))
    hashes = {stored[role]: digest for role, digest in definition.get('sha256', {}).items() if role in stored}
    store = directory / target_id
    parts = []
    for part in definition.get('parts', []):
        path = str(store / f"{part['stem']}.gmd")
        parts.append({'role': part['role'], 'stem': part['stem'], 'bone_count': part.get('bone_count'),
                      'flags': part.get('flags', []), 'path': path})
        if part.get('sha256'):
            hashes[path] = part['sha256']
    return Target(target_id, definition['label'], definition['rig_prefix'], definition['bone_count'],
                  {role: f'{target_id}/{stem}.gmd' for role, stem in roles.items()}, slots, note.strip(),
                  custom_references=refs, custom_hashes=hashes, custom_parts=tuple(parts) if parts else None)


def part_variant_target(base_id: str, stem: str):
    """Target that replaces ONE part (one outfit, hair style or face) of a registered character group.

    Only that part's slot is exported, which keeps a whole-character conversion fast; the other references
    are the base files, which the inspection step needs.
    """
    from um.dragon_targets import ExportSlot, Target, get_target
    base = get_target(base_id)
    part = next((p for p in (base.custom_parts or ()) if p['stem'] == stem), None)
    if part is None:
        raise CustomTargetError(f'{base_id} has no part named {stem}')
    role, size = part['role'], part.get('bone_count') or base.bone_count
    layout = len(base.slots)  # 1: body only, 2: body+face(+hair), 3: body+face+hair
    if role == 'tops':
        slot = ExportSlot('tops', 'tops', stem, ('tops', 'face', 'hair') if layout == 1 else ('tops',), 'tops')
        overrides = ['tops'] + (['face', 'hair'] if layout == 1 else [])
    elif role == 'face':
        slot = ExportSlot('face', 'face', stem, ('face', 'hair') if layout == 2 else ('face',), 'face')
        overrides = ['face'] + (['hair'] if layout == 2 else [])
    else:
        slot = ExportSlot('hair', 'hair', stem, ('hair',), 'hair')
        overrides = ['hair']
    refs = dict(base.custom_references)
    files = dict(base.reference_files)
    for target_role in overrides:
        refs[target_role] = part['path']
        files[target_role] = f'{base_id}/{stem}.gmd'
    return Target(f'{base_id}__{stem}', f'{base.label} / {stem}',
                  stem if role == 'tops' else base.rig_prefix,
                  size if role == 'tops' else base.bone_count, files, (slot,),
                  'Custom part of a character group; compatibility and in-game appearance are unverified.',
                  custom_references=refs, custom_hashes=dict(base.custom_hashes or {}),
                  slot_bone_counts={slot.key: size})


# ---- storage -------------------------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_and_save(definition: dict, files: dict, directory=None, replace: bool = False,
                    part_files: dict | None = None) -> dict:
    """Copy the GMDs into the private store (the only time the originals are read) and write the JSON.

    part_files maps a part's stem to the original file of that part.
    """
    directory = Path(directory) if directory else custom_dir()
    part_files = part_files or {}
    target_id = definition['id']
    store = directory / target_id
    if (store.exists() or (directory / f'{target_id}.json').exists()) and not replace:
        raise CustomTargetError(f'A custom target named {target_id} already exists')
    missing = [p['stem'] for p in definition.get('parts', []) if p['stem'] not in part_files]
    if missing:
        raise CustomTargetError(f'Original files of these parts were not given: {missing[:3]}')
    directory.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.import_', dir=directory))
    try:
        hashes, copies = {}, {}
        for role, path in files.items():
            copy = staging / f'{Path(path).stem}.gmd'
            if not copy.exists():
                shutil.copyfile(path, copy)
            hashes[role] = _sha256(copy)
        parts = []
        for part in definition.get('parts', []):
            copy = staging / f"{part['stem']}.gmd"
            if not copy.exists():
                shutil.copyfile(part_files[part['stem']], copy)
            parts.append(dict(part, sha256=_sha256(copy)))
        saved = dict(definition, sha256=hashes, parts=parts)
        if store.exists():
            shutil.rmtree(store)
        staging.replace(store)
        (directory / f'{target_id}.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n',
                                                     encoding='utf-8')
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return saved


def load_definition(target_id: str, directory=None) -> dict:
    directory = Path(directory) if directory else custom_dir()
    if not target_id.startswith(PREFIX) or '__' in target_id or not re.fullmatch(r'[a-z0-9_]+', target_id):
        raise CustomTargetError(f'Invalid custom target id: {target_id}')
    path = directory / f'{target_id}.json'
    try:
        definition = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CustomTargetError(f'Custom target {target_id} could not be loaded: {exc}') from exc
    if definition.get('schema') not in SUPPORTED_SCHEMAS or definition.get('id') != target_id:
        raise CustomTargetError(f'Custom target {target_id} has an unsupported definition')
    definition.setdefault('parts', [])
    return definition


def list_ids(directory=None) -> list[str]:
    directory = Path(directory) if directory else custom_dir()
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob(PREFIX + '*.json') if re.fullmatch(r'[a-z0-9_]+', p.stem))


def delete_target(target_id: str, directory=None) -> None:
    """Remove one custom target (its JSON and its private GMD copies); nothing else is touched."""
    directory = Path(directory) if directory else custom_dir()
    load_definition(target_id, directory)  # validates the id
    store = directory / target_id
    if store.is_dir() and store.resolve().parent == directory.resolve():
        shutil.rmtree(store)
    (directory / f'{target_id}.json').unlink(missing_ok=True)
