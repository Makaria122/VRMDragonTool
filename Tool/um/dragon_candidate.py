"""Read-only quality report for a private Lost Judgment draft."""
from __future__ import annotations

import json
import math
from pathlib import Path

REGIONS = ('face', 'hair', 'tops')


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Expected a JSON object: {path.name}')
    return data


def check_draft(folder: str | Path) -> dict:
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Select a private draft folder, not a GMD file')
    blockers = []
    try:
        status = _read(root / 'status.json')
        from um.dragon_targets import get_target
        target = get_target(status.get('target_id', 'yagami'))
        regions = tuple(slot.key for slot in target.slots)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {'status': 'QUALITY_CHECK_FAILED',
                'blockers': [f'Missing/invalid private status.json: {exc}']}
    audited = 0
    poses = 0
    for region in regions:
        try:
            build = _read(root / f'{region}_result.json')
            audit = _read(root / f'{region}_audit.json')
            pose = _read(root / f'{region}_pose.json')
            job = _read(root / f'{region}_job.json')
            output = Path(job['working_copy']).resolve(strict=True)
            if not output.is_relative_to(root) or output.suffix.lower() != '.gmd':
                raise ValueError('Candidate GMD must be a private output in selected folder')
            if not build.get('strict_export_reimport') or not audit.get('rest_geometry_verified'):
                raise ValueError('GMD strict reimport / rest geometry audit missing')
            count = build.get('source_mesh_count')
            if type(count) is not int or count < 1 or audit.get('target_bones') != target.bone_count or len(audit['meshes']) != count:
                raise ValueError('Skeleton/mesh count mismatch')
            if not pose.get('poses_evaluated_offline') or pose.get('action_count', 0) < 4:
                raise ValueError('Insufficient offline action samples')
            if pose.get('sample_count') != len(pose.get('samples', [])):
                raise ValueError('Pose sample report truncated')
            for mesh in audit['meshes']:
                value = mesh.get('max_position_delta_m')
                if type(value) not in (float, int) or not math.isfinite(value) or value > 2e-5:
                    raise ValueError('Rest geometry coordinate tolerance failed')
            if region == 'tops':
                samples = pose['samples']
                if not samples:
                    raise ValueError('No tops pose samples')
                worst_p95 = max(s['p95_edge_stretch'] for s in samples)
                worst = max(s['max_edge_stretch'] for s in samples)
                ref_p95 = status.get('original_tops_p95_stretch')
                ref_max = status.get('original_tops_max_stretch')
                if (type(ref_p95) not in (int, float) or type(ref_max) not in (int, float)
                        or not all(math.isfinite(x) and x > 0 for x in (ref_p95, ref_max))):
                    raise ValueError('Missing original-game motion baseline')
                if worst_p95 > ref_p95 * 1.25 or worst > ref_max * 1.5:
                    blockers.append(f'Tops pose deformation exceeds reference: p95 {worst_p95:.3f} vs '
                                    f'{ref_p95:.3f}, worst {worst:.3f} vs {ref_max:.3f}')
            audited += count
            poses += len(pose['samples'])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            blockers.append(f'{region}: incomplete private draft/validation ({exc})')
    if audited != status.get('source_mesh_count'):
        blockers.append('Draft status / audited mesh total disagree')
    if poses != status.get('pose_samples'):
        blockers.append('Draft status / pose sample total disagree')
    return {'status': 'QUALITY_CHECK_FAILED' if blockers else 'MANUAL_REVIEW_REQUIRED',
            'full_gameplay_validated': False,
            'audited_meshes': audited, 'pose_samples': poses, 'blockers': blockers,
            'remaining_checks': ['Appearance and transparency inspection',
                                 'Actual game animation and collision checks']}
