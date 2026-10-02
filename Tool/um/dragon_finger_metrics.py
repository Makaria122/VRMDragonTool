"""Topology-local finger edge strain measurements for private pose reports."""
from __future__ import annotations

import math

FINGER_STEMS=('oya','hito','naka','kusu','koyu')


def finger_edges(mesh):
    """Return edges whose endpoints are both predominantly bound to one finger."""
    names=[group.name for group in mesh.vertex_groups]
    membership=[]
    for vertex in mesh.data.vertices:
        weights={}
        for influence in vertex.groups:
            name=names[influence.group]
            for stem in FINGER_STEMS:
                for side in ('l','r'):
                    if name.startswith(stem) and name.endswith(f'_{side}_n'):
                        key=f'{stem}_{side}'
                        weights[key]=weights.get(key,0)+influence.weight
        membership.append(weights)
    edges=[]
    for edge in mesh.data.edges:
        a,b=edge.vertices
        for stem in FINGER_STEMS:
            for side in ('l','r'):
                key=f'{stem}_{side}'
                if membership[a].get(key,0)>=.5 and membership[b].get(key,0)>=.5:
                    edges.append((a,b,key))
    return edges


def summarize_ratios(samples):
    report={}
    for finger,values in samples.items():
        values=sorted(values)
        if not values:
            continue
        if any(not math.isfinite(x) for x in values):
            raise ValueError('Nonfinite finger edge ratio')
        report[finger]={'samples':len(values),
            'p95_edge_stretch':round(values[int(.95*(len(values)-1))],4),
            'max_edge_stretch':round(values[-1],4),
            'min_edge_stretch':round(values[0],4),
            'fraction_over_1_5':round(sum(x>1.5 for x in values)/len(values),4),
            'fraction_under_0_667':round(sum(x<1/1.5 for x in values)/len(values),4)}
    return report
