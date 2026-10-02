"""Explicit offline target-character layouts supported by the conversion workflow."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExportSlot:
    key: str
    region: str
    stem: str
    source_regions: tuple[str, ...]
    reference_role: str


@dataclass(frozen=True)
class Target:
    id: str
    label: str
    rig_prefix: str
    bone_count: int
    reference_files: dict[str, str]
    slots: tuple[ExportSlot, ...]
    motion_note: str


_TARGETS = {
    "yagami": Target(
        id="yagami", label="Yagami", rig_prefix="c_cl_x_yagami", bone_count=358,
        reference_files={"tops": "LostJudgment_Yagami_Original/tops/c_cl_x_yagami.gmd",
                         "face": "LostJudgment_Yagami_Original/face/c_cl_f_yagami.gmd",
                         "hair": "LostJudgment_Yagami_Original/hair/c_cl_h_yagami.gmd"},
        slots=(ExportSlot("tops", "tops", "c_cl_x_yagami", ("tops",), "tops"),
               ExportSlot("face", "face", "c_cl_f_yagami", ("face",), "face"),
               ExportSlot("hair", "hair", "c_cl_h_yagami", ("hair",), "hair")),
        motion_note="Yagami reference actions and original pose baseline.",
    ),
    "kaito": Target(
        id="kaito", label="Kaito (single-GMD trial)", rig_prefix="c_am_kaito", bone_count=285,
        reference_files={"tops": "Targets/Kaito/c_am_kaito.gmd",
                         "face": "Targets/Kaito/c_am_kaito.gmd",
                         "hair": "Targets/Kaito/c_am_kaito.gmd"},
        slots=(ExportSlot("tops", "tops", "c_am_kaito", ("tops", "face", "hair"), "tops"),),
        motion_note=("Proxy only: the local Yagami action clips are applied to Kaito's shared core bones; "
                     "this is not validation against Kaito-native gameplay animations."),
    ),
}


# Explicit default variants from the private extracted-file investigation.
# Two-file trials route source face+hair into the existing face GMD, never invent
# a missing hair filename. Identity, native motion and runtime layout need review.
_TRIALS = (
    ('sugiura', 'Fumiya Sugiura', 358, 'c_cl_x_sugiura_normal', 'c_cl_f_sugiura', None),
    ('tsukumo', 'Makoto Tsukumo', 285, 'c_cm_x_tsukumo_normal', 'c_cm_f_tsukumo', None),
    ('saori', 'Saori Shirosaki', 211, 'c_cv_x_saori', 'c_cv_f_saori', None),
    ('higashi', 'Toru Higashi', 285, 'c_cm_x_higashi_suit', 'c_cm_f_higashi', None),
    ('tesso', 'Tesso', 285, 'c_am_tesso', None, None),
    ('kuwana', 'Jin Kuwana', 285, 'c_cm_x_kuwana', 'c_cm_f_kuwana', None),
    ('soma', 'Kazuki Soma', 289, 'c_ag_soma', None, None),
    ('akutsu', 'Daimu Akutsu', 285, 'c_am_akutsu', None, None),
    ('genda', 'Ryuzo Genda', 285, 'c_am_genda', None, None),
    ('hoshino', 'Issei Hoshino', 289, 'c_ag_hoshino', None, None),
    ('mafuyu', 'Mafuyu Fujii', 182, 'c_cw_x_mafuyu', 'c_cw_f_mafuyu', 'c_cw_h_mafuyu'),
    ('sawa', 'Yoko Sawa', 182, 'c_aw_sawa', None, None),
)
for _id, _label, _bones, _tops, _face, _hair in _TRIALS:
    _refs = {role: f'Targets/{_id}/{stem}.gmd' for role, stem in
             (('tops', _tops), ('face', _face or _tops), ('hair', _hair or _face or _tops))}
    if not _face:
        _slots = (ExportSlot('tops', 'tops', _tops, ('tops', 'face', 'hair'), 'tops'),)
    else:
        _slots = (ExportSlot('tops', 'tops', _tops, ('tops',), 'tops'),
                  ExportSlot('face', 'face', _face, ('face',) if _hair else ('face', 'hair'), 'face'))
        if _hair:
            _slots += (ExportSlot('hair', 'hair', _hair, ('hair',), 'hair'),)
    _TARGETS[_id] = Target(_id, _label + ' (experimental)', _tops, _bones, _refs, _slots,
        'Experimental extracted-reference layout; identity and game-side slot usage unverified. '
        'Yagami action clips on shared bones are a proxy, NOT native animation validation. '
        + ('No separate hair file: face+hair are exported together in the face slot.'
           if _face and not _hair else ''))


def target_ids() -> tuple[str, ...]:
    return tuple(_TARGETS)


def get_target(target_id: str = "yagami") -> Target:
    if '__' in target_id:
        from um.dragon_variants import variant_target
        return variant_target(target_id)
    try:
        return _TARGETS[target_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported target character: {target_id}") from exc


def target_references(target_id: str, private_data: str | Path | None = None,
                      source_root: str | Path | None = None) -> dict[str, str]:
    spec = get_target(target_id)
    if source_root is not None:
        from um.dragon_asset_catalog import resolve_references
        return resolve_references(spec.reference_files, source_root)
    if private_data is None:
        raise ValueError('private_data or source_root is required')
    root = Path(private_data).expanduser().resolve()
    return {role: str((root / relative).resolve())
            for role, relative in spec.reference_files.items()}
