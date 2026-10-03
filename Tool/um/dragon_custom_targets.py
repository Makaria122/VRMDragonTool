"""User-defined ("Other") targets: GMD files from any Dragon Engine game, registered from the GUI.

The user picks a tops GMD (and optionally face/hair GMDs). The files are inspected read-only in Blender,
checked for the skeleton the fitting code needs, and copied once into Tool/userdata/targets/<id>/ so that the
conversion never touches the game folder. The definition is stored as JSON and shows up in the target list.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

PREFIX = 'custom_'
SCHEMA = 1
ROLES = ('tops', 'face', 'hair')
STEM_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$')
FINGER_WORDS = ('Thumb', 'Index', 'Middle', 'Ring', 'Little')


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


# ---- inspection (Blender, read-only) -------------------------------------------------------------------
def inspect_files(files: dict, blender, addon, runner=None, timeout: int = 600) -> dict:
    """Parse the GMDs with the GMD add-on in a background Blender. Returns {role: parsed dict}."""
    import subprocess
    from um.dragon_log import run_logged
    runner = runner or run_logged
    blender, addon = Path(blender), Path(addon)
    if not blender.is_file():
        raise CustomTargetError('Blender was not found; set it up first (Blender tab)')
    worker = Path(__file__).with_name('dragon_variant_worker.py')
    entries = []
    for role, path in files.items():
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != '.gmd':
            raise CustomTargetError(f'Not a .gmd file: {path}')
        entries.append({'absolute_path': str(path.resolve()), 'source_relative_path': path.name,
                        'model_id': path.stem, 'region': role})
    with tempfile.TemporaryDirectory(prefix='custom_target_') as temp:
        job, out = Path(temp) / 'job.json', Path(temp) / 'parsed.json'
        job.write_text(json.dumps({'addon': str(addon), 'files': entries, 'output': str(out)}), encoding='utf-8')
        command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '1',
                   '--python', str(worker), '--', str(job)]
        try:
            proc = runner(command, 'inspect custom GMDs', timeout)
        except subprocess.TimeoutExpired as exc:
            raise CustomTargetError('Blender took too long to read the GMD files') from exc
        if not out.is_file():
            from um.dragon_log import failure_summary
            raise CustomTargetError('Blender could not read the GMD files: '
                                    + failure_summary(getattr(proc, 'stdout', ''), getattr(proc, 'stderr', '')))
        parsed = json.loads(out.read_text(encoding='utf-8'))
    by_path = {item.get('absolute_path'): item for item in parsed}
    return {role: by_path.get(str(Path(path).resolve()), {}) for role, path in files.items()}


# ---- definition (pure, unit-tested) --------------------------------------------------------------------
def build_definition(files: dict, inspections: dict, label: str | None = None, target_id: str | None = None) -> dict:
    """Validate the inspections and describe the target. Raises CustomTargetError with a readable reason."""
    if 'tops' not in files:
        raise CustomTargetError('A tops GMD (the body) is required')
    unknown = set(files) - set(ROLES)
    if unknown:
        raise CustomTargetError(f'Unknown GMD roles: {sorted(unknown)}')
    from um.dragon_fit import BONE_MAP
    needed = required_target_bones()
    counts, warnings = {}, []
    for role in files:
        item = inspections.get(role) or {}
        name = Path(files[role]).name
        if item.get('load_status') != 'loaded':
            raise CustomTargetError(f'{name} could not be read as a GMD: {item.get("error") or item.get("load_status") or "no result"}')
        if not STEM_PATTERN.match(Path(files[role]).stem):
            raise CustomTargetError(f'Unsupported file name: {name} (use letters, digits, _ . - only)')
        names = set(item.get('bone_names') or [])
        missing = sorted(bone for bone in needed.values() if bone not in names)
        if missing:
            raise CustomTargetError(
                f'{name} does not have the bones this tool needs ({len(missing)} missing, for example '
                f'{", ".join(missing[:6])}). Its skeleton is named differently from the supported Dragon Engine one.')
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
            'warnings': warnings, 'created': datetime.now().isoformat(timespec='seconds')}


def to_target(definition: dict, directory=None):
    """Create the Target object for a stored definition (references are the private copies)."""
    from um.dragon_targets import ExportSlot, Target
    directory = Path(directory) if directory else custom_dir()
    stems = definition['stems']
    layout = definition['layout']
    target_id = definition['id']
    if not target_id.startswith(PREFIX) or '__' in target_id:
        raise CustomTargetError(f'Invalid custom target id: {target_id}')
    store = directory / target_id
    stored = {role: str(store / f'{stem}.gmd') for role, stem in stems.items()}
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
    return Target(target_id, definition['label'], definition['rig_prefix'], definition['bone_count'],
                  {role: f'{target_id}/{stem}.gmd' for role, stem in roles.items()}, slots, note.strip(),
                  custom_references=refs, custom_hashes=hashes)


# ---- storage -------------------------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_and_save(definition: dict, files: dict, directory=None, replace: bool = False) -> dict:
    """Copy the GMDs into the private store (the only time the originals are read) and write the JSON."""
    directory = Path(directory) if directory else custom_dir()
    target_id = definition['id']
    store = directory / target_id
    if (store.exists() or (directory / f'{target_id}.json').exists()) and not replace:
        raise CustomTargetError(f'A custom target named {target_id} already exists')
    directory.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.import_', dir=directory))
    try:
        hashes = {}
        for role, path in files.items():
            copy = staging / f'{Path(path).stem}.gmd'
            shutil.copyfile(path, copy)
            hashes[role] = _sha256(copy)
        saved = dict(definition, sha256=hashes)
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
    if definition.get('schema') != SCHEMA or definition.get('id') != target_id:
        raise CustomTargetError(f'Custom target {target_id} has an unsupported definition')
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
