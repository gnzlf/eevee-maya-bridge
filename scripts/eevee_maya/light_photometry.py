"""Measured VP2 light convention, with an explicit legacy compatibility mode.

Eevee has inverse-square local lights. Other Maya decay modes are matched at a
representative linked receiver, not replaced by an exact per-pixel falloff.
"""
import math

MODES=('viewport2','legacy')
LABELS=(('Aproximar Viewport 2.0','viewport2'),('Conversión anterior de Eevee','legacy'))
CLASSIC=('lambert','blinn','phong')

def receiver_reference(origin, bounds, fallback=5, direction=None):
    """Return a receiver index and distance, preferring a beam-axis hit.

    Bounds must contain linked visible receivers only. An enclosing bound is
    ambiguous; use its centre as fallback rather than zero-distance energy.
    """
    hits=[];near=[]
    for index,(low,high) in enumerate(bounds):
        center=[(a+b)*.5 for a,b in zip(low,high)]
        if direction is not None:
            radius=math.sqrt(sum(((b-a)*.5)**2 for a,b in zip(low,high)))
            if sum((c-p)*d for c,p,d in zip(center,origin,direction))+radius<=0:continue
            enter,leave=0.,float('inf')
            for p,d,a,b in zip(origin,direction,low,high):
                if abs(d)<1e-10:
                    if not a-1e-6<=p<=b+1e-6:leave=-1;break
                else:
                    first,last=sorted(((a-p)/d,(b-p)/d));enter=max(enter,first);leave=min(leave,last)
            if leave>=enter and enter>.001:hits.append((enter,index))
        distance=math.sqrt(sum((max(a,min(b,p))-p)**2 for p,a,b in zip(origin,low,high)))
        if distance<=.001:distance=math.sqrt(sum((c-p)**2 for c,p in zip(center,origin)))
        if distance>.001:near.append((distance,index))
    choices=hits or near
    if not choices:return None,max(.001,fallback)
    distance,index=min(choices)
    return index,max(.001,distance)

def energy(spec, legacy=False):
    kind=spec['kind'];sun=kind=='directionalLight';area=kind in ('areaLight','aiAreaLight')
    intensity=max(0,spec['intensity'])*2**spec.get('exposure',0)
    reference=max(.001,spec.get('decay_reference',5))
    decay=int(spec.get('decay',2))
    calibrated=not legacy and spec.get('intensity_mode')=='viewport2'
    if calibrated:
        reference=max(.001,spec.get('viewport_reference',reference))
        gain=spec.get('receiver_gain',1)
        if sun:value=intensity*gain
        elif area:value=intensity*math.pi*gain*reference**(-(decay if kind=='areaLight' else 0))
        else:value=intensity*4*math.pi*reference**(2-decay)*(math.pi if kind=='ambientLight' else gain)
    else:
        value=intensity*(math.pi if sun else 4*math.pi)
        if not sun:value*=reference**(2-decay)
    if kind=='ambientLight':value*=max(0,min(1,spec.get('ambient_shade',.45)))
    if area:
        if not spec.get('normalize',True):value*=max(.000001,spec.get('size_x',2)*spec.get('size_y',2))
        if spec.get('legacy_intensity',False):value*=12
    return value

def volume_compensation(spec):
    current=energy(spec)
    return energy(spec,legacy=True)/current if current>1e-12 else 1
