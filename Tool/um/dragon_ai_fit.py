"""Ask an installed localhost-only model for bounded local skin-weight corrections.

The model sees derived motion diagnostics, never full GMD/VRM files. Its JSON is
untrusted: names and numeric ranges are checked before an offline worker uses it.
No model is installed/downloaded and no game data is written by this module.
"""
from __future__ import annotations

import http.client
import json
import math
from pathlib import Path

URL = 'http://127.0.0.1:11434/api/chat'
MODEL = 'qwen2.5-coder:7b'


def _summary(report: dict) -> dict:
    if not isinstance(report.get('mesh'), str) or not isinstance(report.get('worst_edges'), list):
        raise ValueError('Expected an offline edge diagnostic report')
    edges = []
    for edge in report['worst_edges'][:4]:
        edges.append({'ratio': round(float(edge['ratio']), 2),
                      'rest_edge_m': round(float(edge['rest_m']), 4),
                      'weights': edge['weights']})
    groups = report.get('bone_pair_groups', [])
    return {'mesh': report['mesh'], 'p95_stretch': round(float(report['p95']), 2),
            'worst_edges': edges,
            'affected_bone_pairs': [{'bones': g['bones'], 'count': g['count']}
                                    for g in groups[:8]]}


def validate(data: dict, reports: list[dict], allowed_bones: set[str]) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get('operations'), list):
        raise ValueError('AI response needs an operations array')
    operations = data['operations']
    if not 1 <= len(operations) <= 8:
        raise ValueError('AI must propose 1-8 bounded operations')
    available = {r['mesh'] for r in reports}
    observed_by_mesh = {
        report['mesh']: ({bone for edge in report['worst_edges']
                          for vertex_weights in edge['weights'] for bone, _ in vertex_weights}
                         | {bone for group in report.get('affected_bone_pairs', [])
                            for bone in group['bones']}) for report in reports}
    validated = []
    for op in operations:
        if not isinstance(op, dict) or set(op) != {'mesh', 'center_bone', 'radius_m', 'strength', 'iterations'}:
            raise ValueError('Unknown/extra fields in AI operation')
        if (not isinstance(op['mesh'], str) or not isinstance(op['center_bone'], str)
                or op['mesh'] not in available
                or op['center_bone'] not in (allowed_bones & observed_by_mesh[op['mesh']])):
            raise ValueError('AI used an unknown mesh or target bone')
        if (type(op['radius_m']) not in (int, float) or type(op['strength']) not in (int, float)
                or not all(math.isfinite(float(op[k])) for k in ('radius_m', 'strength'))
                or not .02 <= op['radius_m'] <= .22 or not .05 <= op['strength'] <= .65):
            raise ValueError('AI operation exceeds bounded radius/strength')
        if type(op['iterations']) is not int or not 1 <= op['iterations'] <= 3:
            raise ValueError('AI iterations must be 1..3')
        validated.append({'mesh': op['mesh'], 'center_bone': op['center_bone'],
                          'radius_m': float(op['radius_m']), 'strength': float(op['strength']),
                          'iterations': op['iterations']})
    return {'schema_version': 2, 'model': MODEL, 'review_only': True,
            'operation': 'edge_anchored_weight_relax', 'operations': validated,
            'geometry_changed': False, 'game_install_authorized': False}


def propose(diagnostic_paths: list[str | Path], rebind_report: str | Path, output: str | Path,
            feedback: dict | None = None) -> dict:
    output = Path(output).expanduser().resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('AI proposal must use a NEW file in an existing private folder')
    names = {p.lower() for p in output.parts}
    program_root=Path(__file__).resolve().parents[1]
    bundle_root=(program_root.parent if (program_root.parent/'Blender'/'blender.exe').is_file()
                 else program_root)
    if 'mods' in names or {'steamapps', 'common'} <= names or output.is_relative_to(bundle_root):
        raise ValueError('AI proposal cannot be saved in game folder')
    reports = [_summary(json.loads(Path(path).read_text(encoding='utf-8'))) for path in diagnostic_paths]
    if not reports or len(reports) > 3:
        raise ValueError('Select 1-3 private motion diagnostics')
    rebind = json.loads(Path(rebind_report).read_text(encoding='utf-8'))
    allowed = {row['target'] for row in rebind['joints']}
    if not allowed or len(allowed)>150:
        raise ValueError('Invalid target bone list')
    observed = sorted(({bone for r in reports for edge in r['worst_edges']
                        for weights in edge['weights'] for bone, _ in weights}
                       | {bone for r in reports for group in r['affected_bone_pairs'] for bone in group['bones']}) & allowed)
    feedback_text = '' if feedback is None else json.dumps(feedback,ensure_ascii=False)
    if len(feedback_text)>2000:
        raise ValueError('Feedback exceeds bounded summary size')
    prompt = ('Propose 1-8 corrections, not defects. EDGE_ANCHORED_WEIGHT_RELAX blends neighboring skin weights '
              'inside radius_m of the worst deformed surface edge influenced by center_bone; the bone is a REGION LABEL, '
              'not the sphere center. Geometry/bones stay unchanged. Preserve finger motion. '
              'Choose mesh names exactly from reports, bones only from: ' + ', '.join(observed) +
              '. radius_m 0.02..0.22, strength 0.05..0.65, iterations 1..3. '
              'Balance LEFT/RIGHT shoulders and finger joints; favor p95 without worsening any region. '
              'Output ONLY JSON {"operations":[{"mesh":"...","center_bone":"...",'
              '"radius_m":0.06,"strength":0.3,"iterations":2}]}. Reports: '
              + json.dumps(reports, ensure_ascii=False) + ' Prior trial feedback: ' + feedback_text)
    payload = json.dumps({'model': MODEL, 'stream': False, 'format': 'json',
                          'messages': [{'role': 'system', 'content': 'Return only bounded JSON skin-fit operations. No code or files.'},
                                       {'role': 'user', 'content': prompt}],
                          'options': {'temperature': .1, 'num_predict': 650}}, ensure_ascii=False).encode('utf-8')
    # Direct loopback socket: no proxy or redirect can leak derived asset diagnostics.
    connection = http.client.HTTPConnection('127.0.0.1', 11434, timeout=90)
    try:
        connection.request('POST', '/api/chat', body=payload, headers={'Content-Type':'application/json'})
        response=connection.getresponse()
        if response.status!=200:
            raise ValueError(f'Local Ollama returned HTTP {response.status}')
        raw=response.read(160_001)
        if len(raw)>160_000:
            raise ValueError('Local model response exceeds size limit')
    finally:
        connection.close()
    envelope = json.loads(raw)
    result = validate(json.loads(envelope['message']['content']), reports, allowed)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return result
