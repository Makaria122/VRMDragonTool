"""Private Lost Judgment/Ash beta: reproducible offline draft and fail-closed review.

This is NOT a general VRM converter or a game installer. Input game references,
Blender previews, motion samples and solver results belong to the user and live
outside the distributable Tool/. A matching VRM hash is required.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

REGIONS = {'tops': 'c_cl_x_yagami', 'face': 'c_cl_f_yagami', 'hair': 'c_cl_h_yagami'}
SCHEMA = 'ash-lj-yagami-offline-beta-1'
GENERIC_SCHEMA = 'vrm-lj-yagami-offline-beta-1'


class BetaError(ValueError):
    pass


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def portable_data_path(path: Path, bundle: Path) -> bool:
    """Allow designated private folders, including ignored Tool/userdata only."""
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'userdata'):
        return True
    bundle=bundle.resolve()
    path=path.resolve()
    return ((bundle/'Blender'/'blender.exe').is_file()
            and any(path.is_relative_to(bundle/name) for name in ('PrivateData','Profiles','ModOutputs')))


def _private(path: Path, bundle: Path) -> None:
    names = {piece.lower() for piece in path.parts}
    repository = Path(__file__).resolve().parents[1]
    if ('mods' in names or {'steamapps', 'common'} <= names
            or (path.is_relative_to(bundle) and not portable_data_path(path,bundle))
            or (path.is_relative_to(repository) and not path.is_relative_to(repository/'userdata'))):
        raise BetaError(f'Beta inputs/outputs must stay outside game and tool: {path}')


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise BetaError(f'Expected a JSON object: {path}')
    return value


def _run(blender: Path, script: Path, arguments: list[Path], progress: Callable[[str], None]) -> None:
    label = f'{script.stem}: {arguments[0].stem}'
    progress(label)
    command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '1',
               '--python', str(script), '--', *(str(path) for path in arguments)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=360)
    except subprocess.TimeoutExpired as exc:
        raise BetaError(f'{label} timed out after 360 seconds') from exc
    if done.returncode or not arguments[-1].is_file():
        lines = (done.stderr + '\n' + done.stdout).splitlines()
        problems = [line.strip() for line in lines if any(mark in line for mark in
                    ('Geometry mismatch', 'Traceback', 'AssertionError', 'RuntimeError', 'ValueError'))]
        detail = '\n'.join(problems[-8:]) if problems else '\n'.join(lines[-8:])
        raise BetaError(f'{label} failed: {detail[-2500:]}')


def build(profile_file: str | Path, vrm_file: str | Path, output_folder: str | Path,
          blender_exe: str | Path, addon_folder: str | Path,
          progress: Callable[[str], None] | None = None) -> dict:
    progress = progress or (lambda message: None)
    profile_file = Path(profile_file).expanduser().resolve(strict=True)
    vrm = Path(vrm_file).expanduser().resolve(strict=True)
    output = Path(output_folder).expanduser().resolve()
    blender = Path(blender_exe).expanduser().resolve(strict=True)
    addon = Path(addon_folder).expanduser().resolve(strict=True)
    bundle = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parents[2] / 'Blender' / 'blender.exe').is_file() else Path(__file__).resolve().parents[1]
    source = _json(profile_file)
    if source.get('schema') not in (SCHEMA, GENERIC_SCHEMA) or not isinstance(source.get('vrm_sha256'), str):
        raise BetaError('Not a Lost Judgment private beta profile')
    profile_vrm = Path(source['source_vrm']).resolve(strict=True)
    if vrm != profile_vrm or _digest(vrm) != source['vrm_sha256']:
        raise BetaError('This beta profile belongs to another VRM; prepare a separate private profile for each avatar')
    template = Path(source['template_dir']).resolve(strict=True)
    action_value = source.get('action_blend')
    action = Path(action_value).resolve(strict=True) if action_value else None
    _private(template, bundle)
    if action is not None:
        _private(action, bundle)
    if (output.exists() or not output.parent.is_dir() or output == template):
        raise BetaError('Choose a NEW private output folder outside the source recipe')
    _private(output, bundle)
    if not blender.is_file() or not (addon / 'yk_gmd_blender' / '__init__.py').is_file():
        raise BetaError('Select local Blender executable and GMD addon folder')
    from um.dragon_targets import get_target
    target = get_target(source.get('target_id', 'yagami'))
    slots = {slot.key: slot for slot in target.slots}
    jobs = {}
    inputs = []
    for region, slot in slots.items():
        job = _json(template / f'{region}_job.json')
        original = Path(job['original_gmd']).resolve(strict=True)
        _private(original, bundle)
        if original.suffix.lower() != '.gmd' or original.name != slot.stem + '.gmd':
            raise BetaError(f'Unexpected private {region} original GMD for {target.label}')
        if job.get('target_bone_count', target.bone_count) != target.bone_count:
            raise BetaError(f'Wrong target rig size in {region} job')
        for entry in job['meshes']:
            preview = Path(entry['blend']).resolve(strict=True)
            _private(preview, bundle)
            inputs.append(preview)
        jobs[region] = job
        inputs.append(original)
    texmap = _json(Path(jobs['tops']['texture_map']).resolve(strict=True))
    dds = Path(jobs['tops']['dds_dir']).resolve(strict=True)
    _private(dds, bundle)
    textures = []
    for image in texmap['images']:
        name = image['filename']
        if Path(name).name != name or not name.endswith('.dds'):
            raise BetaError('Invalid DDS filename in private manifest')
        file = (dds / name).resolve(strict=True)
        if not file.is_relative_to(dds) or _digest(file) != image['sha256']:
            raise BetaError(f'Private DDS mismatch: {name}')
        textures.append(file)
    offsets = source.get('mesh_offsets', {})
    if not isinstance(offsets, dict) or any(region not in slots for region in offsets):
        raise BetaError('Invalid local solver result mapping')
    for assignments in offsets.values():
        for files in assignments.values():
            for key in ('source_data', 'solver_result'):
                path = Path(files[key]).resolve(strict=True)
                _private(path, bundle)
                inputs.append(path)
    baseline_path = None
    baseline = None
    if action is not None:
        baseline_path = Path(source.get('original_pose_report', template / 'tops_original_pose_slotfix.json')).resolve(strict=True)
        _private(baseline_path, bundle)
        baseline = _json(baseline_path)
        if baseline.get('action_count', 0) < 4 or not baseline.get('samples'):
            raise BetaError('Missing validated private original-game motion baseline')
    for file in inputs:
        if not file.is_file():
            raise BetaError(f'Missing private reference: {file}')
    output.mkdir()  # input validation first; only private new folder from here on
    modlog = output / 'MODLOG.md'
    modlog.write_text('# VRM / Lost Judgment — private offline beta\n\n'
                      f'- VRM: `{vrm.name}` (SHA256 `{source["vrm_sha256"]}`).\n'
                      '- Local private original GMD references and VRM-derived DDS; never redistribute.\n'
                      '- Source references, existing MODs, saves and game installation remain unchanged.\n'
                      '- Generated GMD and validation reports are local candidate outputs.\n',
                      encoding='utf-8')
    status_file = output / 'status.json'
    status_file.write_text(json.dumps({'status': 'IN_PROGRESS',
                                       'game_install_changed': False}, indent=2) + '\n', encoding='utf-8')
    try:
        private_dds = output / 'chara' / 'dds_hires' / '00'
        private_dds.mkdir(parents=True)
        for texture in textures:
            shutil.copyfile(texture, private_dds / texture.name)
        progress('私用GMDコピーとDDSを準備しました')
        for region, slot in slots.items():
            target_gmd = output / 'chara' / slot.region / slot.stem / (slot.stem + '.gmd')
            target_gmd.parent.mkdir(parents=True)
            shutil.copyfile(jobs[region]['original_gmd'], target_gmd)
            job = dict(jobs[region])
            job['working_copy'] = str(target_gmd)
            job['addon'] = str(addon)
            job['dds_dir'] = str(private_dds)
            job['target_bone_count'] = target.bone_count
            job['mesh_offsets'] = offsets.get(region, {})
            (output / f'{region}_job.json').write_text(json.dumps(job, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            _run(blender, Path(__file__).with_name('dragon_full_draft_worker.py'),
                 [output / f'{region}_job.json', output / f'{region}_result.json'], progress)
            _run(blender, Path(__file__).with_name('dragon_full_draft_audit.py'),
                 [output / f'{region}_job.json', output / f'{region}_audit.json'], progress)
            if action is not None:
                _run(blender, Path(__file__).with_name('dragon_full_draft_pose.py'),
                     [output / f'{region}_job.json', action, output / f'{region}_pose.json'], progress)
        results = [_json(output / f'{region}_result.json') for region in slots]
        audits = [_json(output / f'{region}_audit.json') for region in slots]
        poses = [_json(output / f'{region}_pose.json') for region in slots] if action is not None else []
        if (any(r.get('strict_export_reimport') is not True for r in results)
                or any(a.get('rest_geometry_verified') is not True for a in audits)
                or (action is not None and any(p.get('action_count', 0) < 4 for p in poses))):
            raise BetaError('Missing strict GMD or required motion validation')
        reference_p95 = max(s['p95_edge_stretch'] for s in baseline['samples']) if baseline else None
        reference_max = baseline['max_edge_stretch'] if baseline else None
        trial_p95 = max(s['p95_edge_stretch'] for s in poses[0]['samples']) if poses else None
        trial_max = poses[0]['max_edge_stretch'] if poses else None
        problems = []
        if poses and (trial_p95 > reference_p95 * 1.25 or trial_max > reference_max * 1.5):
            problems.append(f'動作中の胴体伸縮: p95 {trial_p95:.3f} (元 {reference_p95:.3f}), '
                            f'最大 {trial_max:.3f} (元 {reference_max:.3f})')
        if any(r.get('has_accessory_collapse') for r in results):
            problems.append('髪・尻尾などの補助骨ウェイトが親骨へ縮退している')
        status = {'status': ('MOTION_CHECK_FAILED' if poses else 'GEOMETRY_CHECK_FAILED') if problems else ('MANUAL_REVIEW_REQUIRED' if poses else 'MOTION_NOT_RUN'),
                  'motion_validation': 'RUN' if poses else 'MOTION_NOT_RUN',
                  'motion_quality_passed': bool(poses) and not problems,
                  'geometry_quality_passed':not any(r.get('has_accessory_collapse') for r in results),
                  'manual_review_required': True, 'game_install_changed': False,
                  'profile': source['schema'], 'private_output': str(output),
                  'target_id': target.id,
                  'strict_reimport_regions': len(slots),
                  'source_mesh_count': sum(r['source_mesh_count'] for r in results),
                  'pose_samples': sum(p['sample_count'] for p in poses) if poses else 0,
                  'original_tops_p95_stretch': reference_p95, 'original_tops_max_stretch': reference_max,
                  'draft_tops_p95_stretch': trial_p95, 'draft_tops_max_stretch': trial_max,
                  'finger_diagnostics':poses[0].get('finger_diagnostics',{}) if poses else {},
                  'blockers': problems,
                  'geometry_warnings': [warning for report in audits
                                         for warning in report.get('topology_warnings', [])]}
        status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with modlog.open('a', encoding='utf-8') as log:
            log.write(f'- Strict GMD reimport: {len(slots)} target GMD(s) for {target.label}, '
                      f'{status["source_mesh_count"]} meshes, '
                      f'{status["pose_samples"]} offline action samples.\n'
                      + (f'- Tops p95 edge stretch: {trial_p95:.3f} vs original {reference_p95:.3f}.\n' if poses else '- Motion validation: NOT RUN (no Action provided).\n') +
                      f'- Validation result: **{status["status"]}**.\n'
                      f'- Topology warnings: {len(status["geometry_warnings"])}.\n')
        progress(f'{len(slots)}個の対象GMDの往復・動作点検完了。結果を確認してください。')
        return status
    except Exception as exc:
        status_file.write_text(json.dumps({'status': 'BLOCKED_PIPELINE_ERROR',
                                           'game_install_changed': False, 'error': str(exc)},
                                          ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with modlog.open('a', encoding='utf-8') as log:
            log.write('- Pipeline error; see local status.json.\n')
        raise
