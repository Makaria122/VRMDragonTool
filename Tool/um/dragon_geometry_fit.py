"""Small deterministic bounded per-vertex displacement solver."""
from __future__ import annotations

import math


def weighted_bone_offsets(vertex_group_rows, group_names, source_map, joint_deltas, selected):
    selected=set(selected)
    if not selected<=set(joint_deltas):
        raise ValueError('Selected foot bones lack measured deltas')
    offsets=[]
    for groups in vertex_group_rows:
        offset=[0.0,0.0,0.0]
        for group_index,weight in groups:
            if not 0<=group_index<len(group_names) or not math.isfinite(weight) or weight<0:
                raise ValueError('Invalid vertex group influence')
            target=source_map.get(group_names[group_index])
            if target in selected:
                for axis in range(3):
                    offset[axis]+=joint_deltas[target][axis]*weight
        offsets.append(offset)
    return offsets


def limiting_edge(coordinates, edges, offsets, alpha, max_stretch=1.5):
    """Find the edge closest to the stretch constraint after bounded fitting."""
    if len(coordinates)!=len(offsets) or not 0<=alpha<=1:
        raise ValueError('Invalid bounded fit input')
    best=None
    for a,b in edges:
        before=math.dist(coordinates[a],coordinates[b])
        if before<=1e-5:
            continue
        after=math.dist([coordinates[a][i]+alpha*offsets[a][i] for i in range(3)],
                        [coordinates[b][i]+alpha*offsets[b][i] for i in range(3)])
        ratio=after/before
        if not math.isfinite(ratio):
            raise ValueError('Nonfinite fit edge ratio')
        margin=min(abs(ratio-1/max_stretch),abs(ratio-max_stretch))
        if best is None or margin<best['limit_margin']:
            best={'vertices':[a,b],'original_length_m':round(before,7),
                  'ratio_after_fit':round(ratio,5),'limit_margin':margin}
    if best is not None:
        best['limit_margin']=round(best['limit_margin'],7)
    return best


def bounded_offsets(coordinates, edges, offsets, max_stretch=1.5, iterations=20):
    if len(coordinates)!=len(offsets):
        raise ValueError('Coordinate/offset count mismatch')
    if not math.isfinite(max_stretch) or max_stretch<1:
        raise ValueError('Invalid stretch limit')
    def safe(alpha):
        for a,b in edges:
            before=math.dist(coordinates[a],coordinates[b])
            if before<=1e-5:
                continue
            after_coords=[coordinates[a][i]+alpha*offsets[a][i] for i in range(3)]
            after_coordb=[coordinates[b][i]+alpha*offsets[b][i] for i in range(3)]
            ratio=math.dist(after_coords,after_coordb)/before
            if ratio>max_stretch or ratio<1/max_stretch:
                return False
        return True
    low,high=0.0,1.0
    for _ in range(iterations):
        mid=(low+high)/2
        if safe(mid):low=mid
        else:high=mid
    result=[[coordinates[v][i]+low*offsets[v][i] for i in range(3)]
            for v in range(len(coordinates))]
    return low,result
