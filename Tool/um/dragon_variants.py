"""Explicit offline variant recipes and batch conversion; no runtime model hooks.

A variant is independently fitted/exported, never a renamed copy of another GMD.
Shared replacement paths have an explicit first recipe owner using the SAME source
reference; no differing-reference collision is silently overwritten.
"""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path

# Reviewed layouts plus explicitly approved Sawa age/dead/sitting exceptions.
# Other discovered young/dead/special candidates remain excluded.
# base, variant key, tops override, face override, hair override
ROWS = (
    ('kaito', 'combat_damage04', 'c_am_kaito_c04bd01', None, None),
    ('kaito', 'combat_damage08', 'c_am_kaito_c08bd01', None, None),
    ('kaito', 'boxing', 'c_am_kaito_dlc_bx01', None, None),
    ('kaito', 'workman', 'c_am_kaito_workman', None, None),
    ('kaito', 'cutscene', 'c_cm_x_kaito', 'c_cm_f_kaito', None),
    ('kaito', 'disguise', 'c_cm_x_kaito_henso01', 'c_cm_f_kaito_henso01', None),
    ('kaito', 'suit', 'c_cm_x_kaito_suit', 'c_cm_f_kaito', None),
    ('yagami', 'avatar_outfit', 'c_cl_x_yagami_avatar', None, None),
    ('yagami', 'formal', 'c_cl_x_yagami_formal', None, None),
    ('yagami', 'repair', 'c_cl_x_yagami_repair', None, None),
    ('yagami', 'avatar_face', None, 'c_cl_f_yagami_avatar', None),
    ('yagami', 'ninja_face', None, 'c_cl_f_yagami_ninja', None),
    ('sugiura', 'boxing', 'c_cl_x_sugiura_dlc_bx', None, None),
    ('sugiura', 'taxi', 'c_cl_x_sugiura_taxi', None, None),
    ('sugiura', 'workman', 'c_cl_x_sugiura_workman', None, None),
    ('tsukumo', 'workman', 'c_cm_x_tsukumo_workman', None, None),
    ('higashi', 'apron', 'c_cm_x_higashi_apron', None, None),
    ('higashi', 'boxing', 'c_cm_x_higashi_dlc_bx', None, None),
    ('hoshino', 'glasses', 'c_ag_hoshino_glass', None, None),
    # Event tops have different rest skeletons; measured grouping must not reuse
    # default preparation. The shared face keeps its independently exported owner.
    ('kuwana', 'event_c04', 'c_cm_x_kuwana_c04bd01', None, None),
    ('kuwana', 'event_c10', 'c_cm_x_kuwana_c10bd01', None, None),
    ('sawa', 'age18', 'c_aw_sawa_18', None, None),
    ('sawa', 'dead', 'c_aw_sawa_dead', None, None),
    ('sawa', 'sitting', 'c_aw_sawa_sit', None, None),
)


def variant_target(key):
    from um.dragon_targets import Target, ExportSlot, get_target
    row = next((r for r in ROWS if r[0] + '__' + r[1] == key), None)
    if row is None:
        raise ValueError(f'Unsupported variant: {key}')
    base, name, tops, face, hair = row
    original = get_target(base)
    refs = dict(original.reference_files)
    for role, stem in (('tops', tops), ('face', face), ('hair', hair)):
        if stem:
            refs[role] = f'Variants/{base}/{stem}.gmd'
    if base == 'kaito' and face:
        refs['hair'] = refs['face']
        slots = (ExportSlot('tops', 'tops', tops, ('tops',), 'tops'),
                 ExportSlot('face', 'face', face, ('face', 'hair'), 'face'))
    else:
        slots = tuple(ExportSlot(s.key, s.region, Path(refs[s.reference_role]).stem,
                                 s.source_regions, s.reference_role) for s in original.slots)
        if len(original.slots) == 1:
            refs['face'] = refs['hair'] = refs['tops']
    stem = Path(refs['tops']).stem
    return Target(key, original.label + ' / ' + name + ' (offline variant)', stem,
                  original.bone_count, refs, slots,
                  ('Sawa age/dead/sitting reference; runtime posture/expression unverified. ' if base=='sawa' else
                   'Offline-tested reference recipe; runtime switch usage unverified. ') +
                  'Yagami shared-bone proxy only, not native cutscene validation.')


def variants_for(base):
    from um.dragon_targets import get_target
    get_target(base)
    return [base] + [r[0] + '__' + r[1] for r in ROWS if r[0] == base]


def replacement_ownership(keys):
    """Precompute ownership; reject same destination with a different template."""
    from um.dragon_targets import get_target
    owners = {}
    for key in keys:
        target = get_target(key)
        for slot in target.slots:
            path = f'chara/{slot.region}/{slot.stem}/{slot.stem}.gmd'
            reference = target.reference_files[slot.reference_role]
            if path in owners and owners[path]['reference'] != reference:
                raise ValueError(f'Conflicting variant reference for {path}')
            owners.setdefault(path, {'owner': key, 'reference': reference})
    return owners


def availability(base, private_data=None, source_root=None):
    from um.dragon_targets import target_references, get_target
    if source_root is not None:
        from um.dragon_asset_catalog import available_references
        rows = []
        for key in variants_for(base):
            found = available_references(get_target(key).reference_files, source_root)
            present = len(found) == len(get_target(key).reference_files)
            rows.append({'id': key, 'ready': present,
                         'reason': '' if present else 'registered reference(s) missing; strict validation pending',
                         'found': present, 'validated': False})
        return rows
    if private_data is None:
        raise ValueError('private_data or source_root is required')
    keys = variants_for(base)
    manifest = Path(private_data) / 'TargetDiscovery/variant_reference_validation.json'
    verified = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
    good = set(verified.get('verified_variants', []))
    rows = []
    for key in keys:
        paths = target_references(key, private_data)
        present = all(Path(p).is_file() for p in paths.values())
        hashes_match = True
        if key != base:
            from um.dragon_targets import get_target
            for relative in get_target(key).reference_files.values():
                path = Path(private_data)/relative
                expected = verified.get('reference_sha256', {}).get(relative)
                if not expected or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    hashes_match = False
        ready = present and (key == base or key in good and hashes_match)
        rows.append({'id':key, 'ready':ready,
                     'reason':'' if ready else '参照未検証・strict往復失敗・不足・ハッシュ不一致'})
    return rows


def run_batch(vrm, references, blender, addon, action_blend, baseline_report,
              output, dummy_texture_dir, progress=None, target_id='yagami', variant_ids=None,
              source_root=None):
    from um.dragon_oneclick import run
    from um.dragon_mod_package import combine_mod_folders
    from um.dragon_targets import target_references, get_target
    progress = progress or (lambda text: None)
    output = Path(output).resolve()
    bundle = Path(__file__).resolve().parents[2]
    from um.dragon_beta import _private
    _private(output, bundle)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Batch output must be a new private folder')
    offered = availability(target_id, bundle / 'PrivateData', source_root=source_root)
    if not offered[0]['ready']:
        raise ValueError('Default references missing; cannot run variant batch')
    keys = [r['id'] for r in offered if r['ready']]
    if variant_ids is not None:
        if target_id not in variant_ids or len(set(variant_ids)) != len(variant_ids) or any(k not in keys for k in variant_ids):
            raise ValueError('Selection must include default and only ready registered variants')
        keys = [k for k in keys if k in variant_ids]
    owners = replacement_ownership(keys)
    discovery = bundle / 'PrivateData/TargetDiscovery/variant_coverage_catalog.json'
    coverage = json.loads(discovery.read_text(encoding='utf-8')) if source_root is None and discovery.is_file() else {}
    output.mkdir()
    (output / 'Runs').mkdir()
    report_path = output / 'variant-coverage.json'
    report = {'status': 'IN_PROGRESS', 'target_id': target_id, 'variants': [],
              'replacement_owners': owners, 'game_install_changed': False,
              'runtime_switch_verified': False,
              'excluded_candidates': coverage.get(target_id, []) if source_root is None else
                  sorted({Path(r[2]).stem for r in ROWS if r[0] == target_id and r[2]} -
                         {Path(get_target(k).reference_files['tops']).stem for k in keys if k != target_id}),
              'skipped_variants':[r for r in offered if not r['ready']],
              'unselected_variants':[r['id'] for r in offered if r['ready'] and r['id'] not in keys],
              'coverage_scope':'Registered source references; strict validated per export; not all runtime switches' if source_root is not None else 'Registered offline-validated references only; not all runtime switches'}
    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save()
    filtered = []
    preparation_cache = {}  # measured, in-memory, scoped to this VRM batch only
    try:
        for index, key in enumerate(keys):
            progress(f'モデル切替候補 {index+1}/{len(keys)}: {key}')
            refs = references if key == target_id else target_references(
                key, bundle/'PrivateData' if source_root is None else None, source_root=source_root)
            # A user-selected base reference cannot silently redefine a shared slot.
            if key == target_id:
                declared = target_references(key, bundle/'PrivateData' if source_root is None else None,
                                             source_root=source_root)
                if any(Path(refs[r]).resolve() != Path(declared[r]).resolve() for r in declared):
                    raise ValueError('Variant batch requires the registered default references')
            result = run(vrm, refs, blender, addon, action_blend, baseline_report,
                         output/'Runs'/key, dummy_texture_dir, progress, target_id=key,
                         profile_root=(Path(__file__).resolve().parents[1]/'userdata/Profiles') if source_root is not None else bundle/'Profiles', preparation_cache=preparation_cache)
            mod = Path(result['mod_folder'])
            kept = output / 'OwnedPayloads' / key
            kept.mkdir(parents=True)
            for file in mod.rglob('*'):
                if not file.is_file():
                    continue
                rel = file.relative_to(mod)
                posix = rel.as_posix()
                if file.suffix.lower() == '.gmd':
                    if posix not in owners:
                        raise ValueError(f'Unexpected unregistered GMD in variant payload: {posix}')
                    if owners[posix]['owner'] != key:
                        continue
                if posix == 'MODLOG.md':
                    continue
                dest = kept/rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, dest)
            filtered.append(kept)
            report['variants'].append({'id': key, 'status': result['candidate_status'],
                                      'motion_validation':result.get('motion_validation','MOTION_NOT_RUN' if result['candidate_status']=='MOTION_NOT_RUN' else 'RUN'),
                                      'motion_quality_passed':result.get('motion_quality_passed',result['candidate_status']=='MANUAL_REVIEW_REQUIRED'),
                                      'run': str(output/'Runs'/key),
                                      'owned_gmds': [p for p,o in owners.items() if o['owner']==key],
                                      'skeleton_group':result.get('skeleton_group')})
            save()
        if len(filtered) > 1:
            combined = combine_mod_folders(filtered, output/'ReviewPack',
                                          'VRM '+target_id+' model variants')
            report['mod_folder'] = combined['mod_folder']
        else:
            report['mod_folder'] = str(mod)
        report['adjustment_group_count'] = len(preparation_cache)
        report['motion_failed_variants'] = [r['id'] for r in report['variants'] if r['status'] == 'MOTION_CHECK_FAILED']
        report['motion_unchecked_variants']=[r['id'] for r in report['variants'] if r['motion_validation']=='MOTION_NOT_RUN']
        report['motion_quality_passed'] = all(r['motion_quality_passed'] for r in report['variants'])
        report['status'] = ('VARIANT_PACK_MOTION_CHECK_FAILED' if report['motion_failed_variants'] else
                           'VARIANT_PACK_MOTION_NOT_RUN' if report['motion_unchecked_variants'] else 'VARIANT_PACK_READY_UNVERIFIED')
        # Like single-run ReviewPack, failed motion outputs are review-only, not approved mods.
        if report['motion_failed_variants'] or report['motion_unchecked_variants']:
            warning = 'WARNING: motion checks FAILED for: '+', '.join(report['motion_failed_variants'])+'\nMotion NOT RUN for: '+', '.join(report['motion_unchecked_variants'])+'\nReview-only candidate. Do not treat as validated in-game.\n'
            folder = Path(report['mod_folder'])
            (folder/'VARIANT_REVIEW_WARNING.txt').write_text(warning, encoding='utf-8')
            with (folder/'MODLOG.md').open('a',encoding='utf-8') as log:
                log.write('\n'+warning)
        save()
        return report
    except Exception as exc:
        report['status'] = 'VARIANT_BATCH_FAILED'
        report['error'] = str(exc)
        save()
        raise
