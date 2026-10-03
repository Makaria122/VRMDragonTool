"""Shared helpers to describe and open the result of a task."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tkinter import messagebox

from um.dragon_i18n import tr


def describe(result: dict) -> str:
    """One sentence for the status line."""
    if result.get('status') == 'VARIANT_PACK_PARTIAL':
        return tr('Some parts could not be converted (see failed_variants in variant-coverage.json). The rest were written as review candidates.')
    if result.get('candidate_status') == 'GEOMETRY_CHECK_FAILED':
        return tr('The accessory-bone/geometry check failed. This is a review candidate whose motion check was not run.')
    if result.get('candidate_status') == 'MOTION_NOT_RUN' or result.get('status') == 'VARIANT_PACK_MOTION_NOT_RUN':
        return tr('The motion check was not run. A review candidate that needs in-game checks was written.')
    if result.get('status') == 'VARIANT_PACK_MOTION_CHECK_FAILED':
        return tr('Candidates were written but the motion check failed. See variant-coverage.json.')
    if result.get('avatar_profile_path'):
        return tr('VRM profile created: {0}', result['avatar_profile_path'])
    if result.get('mod_folder'):
        return tr('Mods-format folder created: {0}', result['mod_folder'])
    if result.get('profile'):
        return tr('Saved the beta candidate and validation results: {0}', result['private_output'])
    if result.get('status') in ('BLOCKED', 'QUALITY_CHECK_FAILED'):
        return tr('Validation results are incomplete. Showing the failure reasons and unverified items.')
    if result.get('status') == 'MANUAL_REVIEW_REQUIRED':
        return tr('A candidate was created. Please review the validation results.')
    if result.get('dds_format'):
        return tr('DDS generation finished. Assignment to GMD materials and in-game checks were not done.')
    if result.get('strict_roundtrip'):
        return tr('Round-trip check of the original torso GMD finished. This is not a pass of the VRM port.')
    if 'fit_plan' in result:
        return tr('Working .blend saved. The bone mapping is only a proposal; nothing has been ported.')
    return tr('Pre-inspection finished. This does not guarantee a successful port or GMD import/export compatibility.')


def result_folder(result: dict) -> Path | None:
    value = result.get('mod_folder') or result.get('private_output')
    if not value:
        return None
    folder = Path(value).resolve()
    return folder if folder.is_dir() else None


def open_folder(folder: Path, parent=None) -> None:
    if os.name != 'nt' or folder is None:
        return
    try:
        os.startfile(str(folder))
    except OSError as exc:
        messagebox.showwarning(tr('Output folder'),
                               tr('Output finished but the folder could not be opened: {0}', exc) + f'\n{folder}')


def report_text(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
