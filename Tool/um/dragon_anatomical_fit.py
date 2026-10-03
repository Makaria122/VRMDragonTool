"""Versioned deterministic rest fitting; no game/Blender dependencies."""
import math

VERSION = 'anatomical-rest-v1'
POSE_MODE = 'leg-pose'  # legs follow the target's bone directions instead of standing heights
POSE_MAX_MOVE_M = 1.0


def sub(a,b): return [x-y for x,y in zip(a,b)]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(a):
    length=math.sqrt(dot(a,a))
    if length<1e-6: raise ValueError('Degenerate anatomical segment')
    return [v/length for v in a],length


def recipe(inventory):
    anchors=inventory.get('joint_anchors',{})
    required=('hips','leftLowerLeg','rightLowerLeg','leftFoot','rightFoot')
    if not all(role in anchors for role in required):
        raise ValueError('Anatomical fitting requires hip/knee/ankle anchors')
    ground=inventory['ground_alignment']
    heights=[]
    for key in ('source','target'):
        heights.append([ground[f'{key}_floor_m'],
            sum(anchors[r][key][2] for r in ('leftFoot','rightFoot'))/2,
            sum(anchors[r][key][2] for r in ('leftLowerLeg','rightLowerLeg'))/2,
            anchors['hips'][key][2]])
    for side,values in zip(('source','target'),heights):
        if not all(math.isfinite(x) for x in values) or any(b-a<.005 for a,b in zip(values,values[1:])):
            detail=', '.join(f'{name}={value:.5f}m' for name,value in zip(('floor','ankle','knee','hip'),values))
            raise ValueError(f'Unordered floor/ankle/knee/hip landmarks; manual review required ({side}: {detail})')
    slopes=[(heights[1][i+1]-heights[1][i])/(heights[0][i+1]-heights[0][i]) for i in range(3)]
    pose_mode=any(not .25<=x<=4 for x in slopes)
    if pose_mode:
        # Bent-leg targets (e.g. seated) keep floor<ankle<knee<hip ordering but not standing
        # proportions; unordered landmarks (bad floor, kneeling/lying) still stop above.
        legs=[side+part for side in ('left','right') for part in ('UpperLeg','LowerLeg','Foot','Toes')]
        if not all(role in anchors for role in legs):
            raise ValueError('Leg proportion correction outside supported bounds')
    segments={}
    for side in ('left','right'):
        chains=[[side+'LowerArm',side+'Hand',side+'MiddleProximal']]
        if pose_mode: chains.append([side+'UpperLeg',side+'LowerLeg',side+'Foot',side+'Toes'])
        for finger in ('Thumb','Index','Middle','Ring','Little'):
            parts=('Metacarpal','Proximal','Distal') if side+finger+'Metacarpal' in anchors else ('Proximal','Intermediate','Distal')
            chains.append([side+finger+p for p in parts])
        for chain in chains:
            if not all(role in anchors for role in chain): continue
            for i,role in enumerate(chain):
                if role.endswith('MiddleProximal') and chain[0].endswith('LowerArm'): continue
                current=anchors[role]
                if i+1<len(chain):
                    nxt=anchors[chain[i+1]]
                    vectors={k:sub(nxt[k],current[k]) for k in ('source','target')}
                else:
                    previous=anchors[chain[i-1]]
                    vectors={k:sub(current[k],previous[k]) for k in ('source','target')}
                su,sl=unit(vectors['source']);tu,tl=unit(vectors['target'])
                if not .25<=tl/sl<=4 or dot(su,tu)<-.95:
                    raise ValueError('Unsupported limb segment proportion/orientation')
                segments[current['source_bone']]={'source':current['source'],'target':current['target'],
                    'source_axis':su,'target_axis':tu,'length_ratio':tl/sl}
    if pose_mode:
        return {'version':VERSION,'mode':POSE_MODE,'max_move_m':POSE_MAX_MOVE_M,
                'hand_segments':segments,'game_install_changed':False}
    return {'version':VERSION,'source_heights':heights[0],'target_heights':heights[1],
            'hand_segments':segments,'game_install_changed':False}


def fit_points(points,weights,config):
    if config.get('version')!=VERSION: raise ValueError('Stale anatomical recipe')
    if len(points)!=len(weights): raise ValueError('Weight count mismatch')
    pose_mode=config.get('mode')==POSE_MODE
    max_move=config.get('max_move_m',.5)
    if pose_mode:
        if not 0<max_move<=1.5: raise ValueError('Invalid anatomical move limit')
    else:
        s,t=config['source_heights'],config['target_heights']
        if any(len(v)!=4 or any(not math.isfinite(x) for x in v)
               or any(b-a<.005 for a,b in zip(v,v[1:])) for v in (s,t)):
            raise ValueError('Invalid anatomical heights')
        if abs(s[-1]-t[-1])>1e-4:
            raise ValueError('Hip anchor must remain fixed')
    for seg in config['hand_segments'].values():
        for key in ('source','target','source_axis','target_axis'):
            if len(seg[key])!=3 or not all(math.isfinite(x) for x in seg[key]):
                raise ValueError('Invalid anatomical segment')
        if (not .25<=seg['length_ratio']<=4
                or dot(seg['source_axis'],seg['target_axis'])<-.95
                or any(abs(dot(seg[key],seg[key])-1)>1e-5 for key in ('source_axis','target_axis'))):
            raise ValueError('Unsupported anatomical segment')
    def height(z):
        if pose_mode: return z
        if z>=s[-1]: return z
        index=next((i for i in range(3) if z<=s[i+1]),2)
        return t[index]+(z-s[index])*(t[index+1]-t[index])/(s[index+1]-s[index])
    result=[]
    for point,influences in zip(points,weights):
        if (len(point)!=3 or not all(math.isfinite(x) for x in point)
                or any(not math.isfinite(w) or w<0 for w in influences.values())):
            raise ValueError('Invalid anatomical vertex/weight')
        p=list(point);p[2]=height(p[2])
        shift=[0.,0.,0.];total=sum(influences.values())
        if total<=0: raise ValueError('Unweighted anatomical vertex')
        for name,weight in influences.items():
            seg=config['hand_segments'].get(name)
            if seg is None: continue
            v=sub(point,seg['source']);a,b=seg['source_axis'],seg['target_axis']
            # Minimal rotation plus axial scaling; retains the VRM's cross-section.
            axis=cross(a,b);c=dot(a,b);av=cross(axis,v);aav=cross(axis,av)
            rotated=[v[i]+av[i]+aav[i]/(1+c) for i in range(3)]
            along=dot(v,a)*(seg['length_ratio']-1)
            mapped=[seg['target'][i]+rotated[i]+b[i]*along for i in range(3)]
            for i in range(3): shift[i]+=(mapped[i]-point[i])*weight/total
        p=[p[i]+shift[i] for i in range(3)]
        if not all(math.isfinite(x) for x in p) or math.dist(p,point)>max_move:
            raise ValueError(f'Anatomical correction exceeds {max_move*100:.0f}cm or is nonfinite')
        result.append(p)
    return result
