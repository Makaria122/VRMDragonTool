"""Read-only foot-support measurements; names like Bandage_Foot are not evidence."""
import math


def foot_weighted_minimum(vertices, foot_groups, threshold=0.25):
    """vertices: iterable of (world_z, {group_name: weight})."""
    values=[]
    for z, weights in vertices:
        total=sum(w for w in weights.values() if w>0)
        foot=sum(w for name,w in weights.items() if name in foot_groups and w>0)
        if total>0 and foot/total>=threshold and math.isfinite(z):
            values.append(z)
    return min(values) if values else None


def support_floor(candidates, ankle_z, side):
    # Foot accessories above the ankle cannot be the support surface.
    valid=[(name,z) for name,z in candidates if z is not None and math.isfinite(z)
           and z<=ankle_z-0.005]
    if not valid:
        raise ValueError(f'{side}: no foot-weighted support surface below ankle; manual review required')
    floor=min(z for _,z in valid)
    return floor,sorted(name for name,z in valid if z<=floor+0.002)
