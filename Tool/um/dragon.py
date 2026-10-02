"""VRM/Dragon Engine desktop and CLI: inspect plus private offline drafts.

Never changes game archives, installed mods or saves. Beta output is not game-ready.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from um.dragon_fit import fit_plan
from um.dragon_beta import portable_data_path

MAX_JSON = 64 * 1024 * 1024
CORE_BONES = (
    "hips", "spine", "head", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightUpperArm", "rightLowerArm", "rightHand", "leftUpperLeg",
    "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot",
)
FIT_BONES = (
    "neck", "leftShoulder", "rightShoulder", "leftThumbProximal",
    "leftIndexProximal", "leftMiddleProximal", "leftRingProximal",
    "leftLittleProximal", "rightThumbProximal", "rightIndexProximal",
    "rightMiddleProximal", "rightRingProximal", "rightLittleProximal",
)


class InspectionError(ValueError):
    """Input cannot be inspected safely or is not a recognized file."""


def _glb_json(path: Path) -> dict:
    with path.open("rb") as f:
        header = f.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise InspectionError("VRM is not a binary glTF (GLB) file")
        version, declared_size = struct.unpack_from("<II", header, 4)
        if version != 2 or declared_size != path.stat().st_size:
            raise InspectionError("Unsupported GLB version or incorrect file length")
        chunk = f.read(8)
        if len(chunk) != 8:
            raise InspectionError("Missing GLB JSON chunk")
        json_size, chunk_kind = struct.unpack("<I4s", chunk)
        if chunk_kind != b"JSON" or not 0 < json_size <= MAX_JSON or 20 + json_size > declared_size:
            raise InspectionError("Invalid or excessively large GLB JSON chunk")
        try:
            data = json.loads(f.read(json_size).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InspectionError("Invalid GLB JSON") from exc
    if not isinstance(data, dict):
        raise InspectionError("GLB JSON root must be an object")
    return data


def inspect_vrm(path: str | Path) -> dict:
    path = Path(path).expanduser().resolve(strict=True)
    gltf = _glb_json(path)
    ext = gltf.get("extensions", {})
    if not isinstance(ext, dict):
        raise InspectionError("Invalid VRM extensions")
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    skins = gltf.get("skins", [])
    if not isinstance(nodes, list) or not isinstance(meshes, list) or not isinstance(skins, list):
        raise InspectionError("Invalid glTF node, mesh or skin table")
    if "VRMC_vrm" in ext:
        vrm_version = "1.0"
        vrm_ext = ext["VRMC_vrm"]
        if not isinstance(vrm_ext, dict) or not isinstance(vrm_ext.get("humanoid", {}), dict):
            raise InspectionError("Invalid VRM 1.0 extension")
        bones = vrm_ext.get("humanoid", {}).get("humanBones", {})
        if not isinstance(bones, dict):
            raise InspectionError("Invalid VRM 1.0 humanoid table")
        bone_nodes = {name: entry.get("node") for name, entry in bones.items()
                      if isinstance(entry, dict)}
    elif "VRM" in ext:
        vrm_version = "0.x"
        vrm_ext = ext["VRM"]
        if not isinstance(vrm_ext, dict) or not isinstance(vrm_ext.get("humanoid", {}), dict):
            raise InspectionError("Invalid VRM 0.x extension")
        bones = vrm_ext.get("humanoid", {}).get("humanBones", [])
        if not isinstance(bones, list):
            raise InspectionError("Invalid VRM 0.x humanoid table")
        bone_nodes = {entry.get("bone"): entry.get("node") for entry in bones
                      if isinstance(entry, dict) and isinstance(entry.get("bone"), str)}
    else:
        raise InspectionError("No VRM 0.x or 1.0 humanoid extension found")
    bone_nodes = {k: v for k, v in bone_nodes.items()
                  if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(nodes)}
    missing_core = [n for n in CORE_BONES if n not in bone_nodes]
    missing_fit = [n for n in FIT_BONES if n not in bone_nodes]
    primitive_count = 0
    missing_skin_attrs = 0
    missing_uv = 0
    for mesh in meshes:
        if not isinstance(mesh, dict):
            raise InspectionError("Invalid glTF mesh entry")
        primitives = mesh.get("primitives", [])
        if not isinstance(primitives, list):
            raise InspectionError("Invalid glTF primitive table")
        for primitive in primitives:
            if not isinstance(primitive, dict):
                raise InspectionError("Invalid glTF primitive")
            attrs = primitive.get("attributes", {})
            if not isinstance(attrs, dict):
                raise InspectionError("Invalid primitive attributes")
            primitive_count += 1
            if not {"JOINTS_0", "WEIGHTS_0"} <= attrs.keys():
                missing_skin_attrs += 1
            if "TEXCOORD_0" not in attrs:
                missing_uv += 1
    issues = []
    if missing_core:
        issues.append("Missing core humanoid bones: " + ", ".join(missing_core))
    if missing_fit:
        issues.append("Missing optional fit landmarks: " + ", ".join(missing_fit))
    if not meshes or not skins:
        issues.append("No mesh or skin detected")
    if missing_skin_attrs:
        issues.append(f"{missing_skin_attrs} primitives lack joint/weight attributes")
    if missing_uv:
        issues.append(f"{missing_uv} primitives lack primary UVs")
    return {
        "path": str(path), "version": vrm_version, "nodes": len(nodes),
        "meshes": len(meshes), "primitives": primitive_count,
        "skins": len(skins), "humanoid_bones": len(bone_nodes),
        "missing_core_bones": missing_core, "missing_fit_landmarks": missing_fit,
        "issues": issues,
    }


def bundled_test_references(bundle: str | Path) -> dict[str, str]:
    """Discover locally copied private tests beside, never inside, a portable bundle."""
    bundle = Path(bundle)
    folder = bundle / 'PrivateData' / 'LostJudgment_Yagami_Original'
    names = {"tops": "c_cl_x_yagami", "face": "c_cl_f_yagami", "hair": "c_cl_h_yagami"}
    paths = {role: folder / role / f"{name}.gmd" for role, name in names.items()}
    return {role: str(path) for role, path in paths.items()} if all(p.is_file() for p in paths.values()) else {}


def inspect_gmd(path: str | Path) -> dict:
    """Check the header only. Never claim a full parse/export from a signature."""
    path = Path(path).expanduser().resolve(strict=True)
    with path.open("rb") as f:
        header = f.read(16)
    if len(header) < 16 or header[:4] != b"GSGM":
        raise InspectionError(f"Not a recognized GMD header: {path.name}")
    return {"path": str(path), "bytes": path.stat().st_size,
            "header_hex": header.hex(), "format_verified": False}


def inspect(vrm: str | Path, tops: str | Path, face: str | Path | None = None,
            hair: str | Path | None = None) -> dict:
    avatar = inspect_vrm(vrm)
    references = {"tops": inspect_gmd(tops)}
    if face:
        references["face"] = inspect_gmd(face)
    if hair:
        references["hair"] = inspect_gmd(hair)
    warnings = list(avatar["issues"])
    warnings.append("GMD headers only: Blender import/export and motion tests have NOT run")
    if not face or not hair:
        warnings.append("Face and hair references are needed before a full-character build")
    return {"schema_version": 1, "profile": "lost-judgment-yagami-preflight",
            "vrm": avatar, "references": references, "warnings": warnings,
            "build_ready": False, "installed": False}


def inspect_blender(vrm: str | Path, tops: str | Path, blender: str | Path,
                    addon: str | Path, face: str | Path | None = None,
                    hair: str | Path | None = None, timeout: int = 240,
                    workspace: str | Path | None = None,
                    target_id: str = "yagami") -> dict:
    """Strictly import local files; optionally save a new offline Blender workspace."""
    preflight = inspect(vrm, tops, face, hair)
    if workspace is not None:
        workspace = Path(workspace).expanduser().resolve()
        program_root = Path(__file__).resolve().parents[1]
        bundle_root = program_root.parent if (program_root.parent / "Blender" / "blender.exe").is_file() else program_root
        if (workspace.suffix.lower() != ".blend" or workspace.exists()
                or not workspace.parent.is_dir() or (workspace.is_relative_to(bundle_root)
                    and not portable_data_path(workspace,bundle_root))):
            raise InspectionError("Choose a NEW .blend outside the program/bundle in an existing folder")
    blender = Path(blender).expanduser().resolve(strict=True)
    addon = Path(addon).expanduser().resolve(strict=True)
    if not blender.is_file() or not (addon / "yk_gmd_blender" / "__init__.py").is_file():
        raise InspectionError("Select a Blender executable and the local GMD addon source folder")
    from um.dragon_targets import get_target
    target_spec = get_target(target_id)
    job = {"vrm": preflight["vrm"]["path"], "addon": str(addon),
           "target_id": target_id,
           "references": {k: v["path"] for k, v in preflight["references"].items()}}
    if workspace is not None:
        job["workspace"] = str(workspace)
    worker = Path(__file__).with_name("dragon_blender_worker.py")
    with tempfile.TemporaryDirectory(prefix="um-dragon-") as temp:
        source = Path(temp) / "job.json"
        target = Path(temp) / "result.json"
        source.write_text(json.dumps(job), encoding="utf-8")
        command = [str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(worker), "--", str(source), str(target)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise InspectionError(f"Blender inspection timed out after {timeout}s") from exc
        if proc.returncode or not target.is_file():
            detail = (proc.stderr + "\n" + proc.stdout)[-2500:].strip()
            raise InspectionError(f"Blender inspection failed (exit {proc.returncode}): {detail}")
        try:
            result = json.loads(target.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise InspectionError("Invalid Blender inspection report") from exc
    if (not isinstance(result, dict) or result.get("strict_gmd_import") is not True
            or not isinstance(result.get("references"), dict)
            or set(result["references"]) != set(preflight["references"])):
        raise InspectionError("Blender did not verify every selected GMD reference")
    top_counts = result.get("references", {}).get("tops", {}).get("bone_counts", [])
    if target_spec.bone_count not in top_counts:
        raise InspectionError(f"Target {target_spec.label} requires a {target_spec.bone_count}-bone tops rig; found {top_counts}")
    preflight["target_id"] = target_spec.id
    preflight["target_bone_count"] = target_spec.bone_count
    preflight["target_rig_prefix"] = target_spec.rig_prefix
    preflight["blender_inspection"] = result
    for role in result.get("references", {}):
        if role in preflight["references"]:
            preflight["references"][role]["strict_import_verified"] = True
    preflight["warnings"] = [w for w in preflight["warnings"] if not w.startswith("GMD headers only:")]
    preflight["warnings"].append("Strict import passed; export, motion, fit and game checks have NOT run")
    if workspace is not None:
        inputs = result.get("fit_inputs")
        if (result.get("workspace") != str(workspace) or not workspace.is_file()
                or workspace.stat().st_size == 0 or not isinstance(inputs, dict)
                or not all(isinstance(inputs.get(k), list) for k in
                           ("vrm_bones", "vertex_groups", "target_bones"))):
            raise InspectionError("Blender workspace report is incomplete")
        preflight["fit_plan"] = fit_plan(_glb_json(Path(preflight["vrm"]["path"])),
                                         inputs["vrm_bones"], inputs["vertex_groups"],
                                         inputs["target_bones"])
        preflight["warnings"].append("Workspace is imported reference geometry only; NOT a retargeted character")
    return preflight


def roundtrip_gmd(source: str | Path, blender: str | Path, addon: str | Path,
                  output: str | Path, timeout: int = 240,
                  expected_bone_count: int = 358) -> dict:
    """Strict export/reimport of one original target into a NEW offline copy."""
    reference = inspect_gmd(source)
    source = Path(reference["path"])
    output = Path(output).expanduser().resolve()
    blender = Path(blender).expanduser().resolve(strict=True)
    addon = Path(addon).expanduser().resolve(strict=True)
    program_root = Path(__file__).resolve().parents[1]
    bundle_root = (program_root.parent if (program_root.parent / "Blender" / "blender.exe").is_file()
                   else program_root)
    parts = {part.lower() for part in output.parts}
    if (output.suffix.lower() != ".gmd" or output.exists() or output == source
            or not output.parent.is_dir() or (output.is_relative_to(bundle_root)
                and not portable_data_path(output,bundle_root))
            or {"steamapps", "common"} <= parts or "mods" in parts):
        raise InspectionError("Choose a NEW offline .gmd outside the tool and game directories")
    if not blender.is_file() or not (addon / "yk_gmd_blender" / "__init__.py").is_file():
        raise InspectionError("Select Blender and the local GMD addon source folder")
    # The exporter needs the file's original hierarchy/header as a template.
    with output.open("xb") as target_file, source.open("rb") as source_file:
        shutil.copyfileobj(source_file, target_file)
    worker = Path(__file__).with_name("dragon_roundtrip_worker.py")
    with tempfile.TemporaryDirectory(prefix="um-dragon-roundtrip-") as temp:
        job = Path(temp) / "job.json"
        result_path = Path(temp) / "result.json"
        job.write_text(json.dumps({"source": str(source), "target": str(output),
                                   "addon": str(addon),
                                   "expected_bone_count": expected_bone_count}), encoding="utf-8")
        command = [str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(worker), "--", str(job), str(result_path)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise InspectionError(f"Blender timed out; private working copy remains at {output}") from exc
        if proc.returncode or not result_path.is_file():
            detail = (proc.stderr + "\n" + proc.stdout)[-2500:].strip()
            raise InspectionError(f"Roundtrip failed; private copy remains at {output}: {detail}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("strict_roundtrip") is not True or result.get("working_copy") != str(output):
        raise InspectionError("Roundtrip result could not be verified")
    return result


def register(sub):
    ap = sub.add_parser("dragon", help="VRM / Dragon Engine preflight and private offline beta")
    commands = ap.add_subparsers(dest="dragon_cmd", required=True)
    gui = commands.add_parser("gui", help="Open the desktop preflight window")
    gui.set_defaults(func=lambda args: launch_gui())
    check = commands.add_parser("inspect", help="Inspect local VRM and GMD headers")
    check.add_argument("--vrm", required=True)
    check.add_argument("--tops", required=True)
    check.add_argument("--face")
    check.add_argument("--hair")
    check.add_argument("--out", help="New JSON report path (never overwrites)")
    check.set_defaults(func=run_inspect)
    deep = commands.add_parser("inspect-blender", help="Strict import in disposable Blender process")
    for action in check._actions:
        if action.dest in ("vrm", "tops", "face", "hair", "out"):
            deep.add_argument(*action.option_strings, required=action.required,
                              help=action.help)
    deep.add_argument("--blender", required=True, help="Local Blender 3.2-5.1 executable")
    deep.add_argument("--addon", required=True, help="Local GMD addon source folder")
    deep.set_defaults(func=run_inspect)
    prepare = commands.add_parser("prepare", help="Create a NEW offline .blend + bone mapping proposal")
    for action in deep._actions:
        if action.dest in ("vrm", "tops", "face", "hair", "blender", "addon", "out"):
            prepare.add_argument(*action.option_strings, required=action.required, help=action.help)
    prepare.add_argument("--workspace", required=True, help="New .blend outside the tool folder")
    prepare.set_defaults(func=run_inspect)
    roundtrip = commands.add_parser("roundtrip", help="Strict GMD export/reimport to a NEW offline copy")
    roundtrip.add_argument("--source", required=True, help="Owned, extracted reference GMD")
    roundtrip.add_argument("--output", required=True, help="New private GMD path")
    roundtrip.add_argument("--blender", required=True)
    roundtrip.add_argument("--addon", required=True)
    roundtrip.add_argument("--out", help="New JSON report path")
    roundtrip.set_defaults(func=run_inspect)
    tex = commands.add_parser("textures", help="Extract embedded VRM base color images to private DXT5 DDS")
    tex.add_argument("--vrm", required=True)
    tex.add_argument("--output-dir", required=True, help="New private folder, not inside tool or game")
    tex.set_defaults(func=run_inspect)
    candidate = commands.add_parser("candidate", help="Read-only quality gate for a private offline draft")
    candidate.add_argument("--folder", required=True, help="Private draft folder containing status.json")
    candidate.set_defaults(func=run_inspect)
    ai = commands.add_parser("ai-propose", help="LOCAL Ollama proposes bounded offline weight corrections")
    ai.add_argument("--diagnostic", action="append", required=True, help="1-3 private motion edge reports")
    ai.add_argument("--rebind", required=True, help="Private target/source joint report")
    ai.add_argument("--output", required=True, help="New private JSON proposal; never a game MOD")
    ai.set_defaults(func=run_inspect)
    beta = commands.add_parser("beta-build", help="Ash-only private offline candidate + 4-action validation; NEVER installs")
    beta.add_argument("--profile", required=True, help="Private Ash beta-profile.json outside Tool")
    beta.add_argument("--vrm", required=True, help="The exact VRM referenced by the private profile")
    beta.add_argument("--output-dir", required=True, help="NEW private folder, outside game and Tool")
    beta.add_argument("--blender", required=True)
    beta.add_argument("--addon", required=True)
    beta.set_defaults(func=run_inspect)
    all_in_one = commands.add_parser("all", help="One-click private VRM → Mods-format review workflow (never installs)")
    for role in ("vrm", "tops", "face", "hair", "blender", "addon", "action-blend", "baseline", "output-dir"):
        all_in_one.add_argument("--" + role, required=True)
    all_in_one.set_defaults(func=run_inspect)


def run_inspect(args):
    try:
        if getattr(args, "out", None) and Path(args.out).expanduser().exists():
            raise FileExistsError(f"Report already exists: {args.out}")
        mode = getattr(args, "dragon_cmd", "inspect")
        if mode == "all":
            from um.dragon_oneclick import run
            report = run(args.vrm, {role: getattr(args, role) for role in ('tops','face','hair')},
                         args.blender, args.addon, args.action_blend, args.baseline,
                         args.output_dir, progress=lambda text: print(text, file=sys.stderr))
        elif mode == "beta-build":
            from um.dragon_beta import build
            report = build(args.profile, args.vrm, args.output_dir, args.blender, args.addon,
                           progress=lambda message: print(message, file=sys.stderr))
        elif mode == "ai-propose":
            from um.dragon_ai_fit import propose
            report = propose(args.diagnostic, args.rebind, args.output)
        elif mode == "candidate":
            from um.dragon_candidate import check_draft
            report = check_draft(args.folder)
        elif mode == "textures":
            from um.dragon_textures import extract
            report = extract(args.vrm, args.output_dir)
        elif mode == "roundtrip":
            report = roundtrip_gmd(args.source, args.blender, args.addon, args.output)
        elif mode in ("inspect-blender", "prepare"):
            report = inspect_blender(args.vrm, args.tops, args.blender, args.addon,
                                     args.face, args.hair,
                                     workspace=args.workspace if mode == "prepare" else None)
        else:
            report = inspect(args.vrm, args.tops, args.face, args.hair)
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if getattr(args, "out", None):
            out = Path(args.out).expanduser()
            # x mode never overwrites an existing report; don't create arbitrary directories.
            with out.open("x", encoding="utf-8") as f:
                f.write(text)
        print(text, end="")
        if mode == "candidate" and not report["install_authorized"]:
            raise SystemExit(2)  # no downstream script may mistake the read-only screen for approval
    except (ValueError, FileNotFoundError, PermissionError, OSError) as exc:
        raise SystemExit(f"dragon {getattr(args, 'dragon_cmd', 'inspect')}: {exc}") from exc


def launch_gui():
    from um.dragon_gui import main
    main()
