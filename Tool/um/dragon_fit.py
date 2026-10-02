"""Conservative humanoid-to-Lost-Judgment bone correspondence suggestions.

This is a proposal only. No meshes, vertex groups or Blender actions are modified.
"""
from __future__ import annotations


BONE_MAP = {
    "hips": "ketu_c_n", "spine": "kosi_c_n", "chest": "mune_c_n",
    "neck": "kubi_c_n", "head": "face_c_n",
}
for side, suffix in (("left", "l"), ("right", "r")):
    BONE_MAP.update({
        f"{side}Shoulder": f"kata_{suffix}_n",
        f"{side}UpperArm": f"ude1_{suffix}_n", f"{side}LowerArm": f"ude2_{suffix}_n",
        f"{side}Hand": f"ude3_{suffix}_n",
        f"{side}UpperLeg": f"asi1_{suffix}_n", f"{side}LowerLeg": f"asi2_{suffix}_n",
        f"{side}Foot": f"asi3_{suffix}_n", f"{side}Toes": f"asi4_{suffix}_n",
    })
    for finger, stem in (("Thumb", "oya"), ("Index", "hito"), ("Middle", "naka"),
                         ("Ring", "kusu"), ("Little", "koyu")):
        for part, number in (("Proximal", 1), ("Intermediate", 2), ("Distal", 3)):
            BONE_MAP[f"{side}{finger}{part}"] = f"{stem}{number}_{suffix}_n"


def humanoid_nodes(gltf: dict) -> dict[str, str]:
    nodes = gltf["nodes"]
    ext = gltf["extensions"]
    if "VRMC_vrm" in ext:
        source = {role: spec.get("node") for role, spec in
                  ext["VRMC_vrm"]["humanoid"]["humanBones"].items()}
    else:
        source = {spec["bone"]: spec.get("node") for spec in ext["VRM"]["humanoid"]["humanBones"]}
    return {role: nodes[idx].get("name", "") for role, idx in source.items()
            if type(idx) is int and 0 <= idx < len(nodes) and isinstance(nodes[idx], dict)}


def fit_plan(gltf: dict, vrm_bones: list[str], vertex_groups: list[str],
             target_bones: list[str]) -> dict:
    named = humanoid_nodes(gltf)
    source = set(vrm_bones)
    groups = set(vertex_groups)
    target = set(target_bones)
    targets = dict(BONE_MAP)
    # VRM 1.0 thumbs may use Metacarpal/Proximal/Distal for three
    # weighted segments; VRM 0.x commonly uses Proximal/Intermediate/Distal.
    # Do not collapse the first 1.0 segment onto the wrist when it is one of
    # exactly these three humanoid roles.
    for side,suffix in (("left","l"),("right","r")):
        if (f"{side}ThumbMetacarpal" in named and f"{side}ThumbProximal" in named
                and f"{side}ThumbDistal" in named and f"{side}ThumbIntermediate" not in named):
            targets[f"{side}ThumbMetacarpal"] = f"oya1_{suffix}_n"
            targets[f"{side}ThumbProximal"] = f"oya2_{suffix}_n"
    matched = []
    unresolved = []
    for role, target_name in targets.items():
        if role not in named:
            unresolved.append({"role": role, "reason": "VRM humanoid role missing"})
            continue
        name = named[role]
        if not name or name not in source:
            unresolved.append({"role": role, "source_node": name, "reason": "Blender source bone not found"})
        elif target_name not in target:
            unresolved.append({"role": role, "target_bone": target_name,
                               "reason": "Game target bone not found"})
        else:
            matched.append({"role": role, "source_bone": name, "target_bone": target_name,
                            "source_vertex_group": name in groups})
    mapped_groups = {item["source_bone"] for item in matched if item["source_vertex_group"]}
    # Non-humanoid hair/clothing groups often hang from a mapped humanoid parent.
    # These are *review hints* only; rigidly collapsing them can ruin clothing motion.
    parents = {}
    by_name = {}
    for index, node in enumerate(gltf["nodes"]):
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("name"), str):
            by_name.setdefault(node["name"], []).append(index)
        children = node.get("children", [])
        if not isinstance(children, list):
            continue
        for child in children:
            if type(child) is int and 0 <= child < len(gltf["nodes"]):
                parents[child] = index
    known = {item["source_bone"]: item for item in matched}
    suggestions = []
    for name in sorted(groups - mapped_groups):
        indices = by_name.get(name, [])
        if len(indices) != 1:
            continue
        current = indices[0]
        visited = {current}
        while current in parents and parents[current] not in visited:
            current = parents[current]
            visited.add(current)
            parent_node = gltf["nodes"][current]
            ancestor = parent_node.get("name") if isinstance(parent_node, dict) else None
            if isinstance(ancestor, str) and ancestor in known:
                suggestions.append({"source_group": name, "ancestor": ancestor,
                                    "suggested_target": known[ancestor]["target_bone"],
                                    "confidence": "review_only"})
                break
    return {"status": "proposal_only", "matched_roles": matched, "unresolved_roles": unresolved,
            "unmapped_vertex_groups": sorted(groups - mapped_groups),
            "accessory_parent_hints": suggestions,
            "source_bone_count": len(source), "source_vertex_group_count": len(groups),
            "target_bone_count": len(target), "weights_transferred": False,
            "geometry_aligned": False, "export_verified": False}
