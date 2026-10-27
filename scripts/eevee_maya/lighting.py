"""Numerically stable approximation of Maya spot angular falloff."""
import math


def set_light_visibility(obj, visible):
    """Do not dirty Blender RNA merely to repeat an unchanged panel state."""
    hidden = not visible
    if obj.hide_viewport != hidden:
        obj.hide_viewport = hidden
    if obj.hide_render != hidden:
        obj.hide_render = hidden


def same_light_links(current, previous):
    """Missing fields differ from explicit empty lists (no receivers)."""
    return previous is not None and all(
        (field in current) == (field in previous) and current.get(field) == previous.get(field)
        for field in ('receivers', 'shadow_blockers'))


def expand_spot_profiles(lights):
    result = []
    for spec in lights:
        dropoff = max(0, spec.get('dropoff', 0))
        if spec['kind'] != 'spotLight' or dropoff <= .001:
            result.append(spec)
            continue
        cone = max(.001, min(math.pi-.001, spec['cone_angle']))
        inner = max(0, cone + 2*min(0, spec.get('penumbra', 0)))
        edge = max(0, math.cos(inner*.5)) ** dropoff
        result.append(dict(spec, intensity=spec['intensity']*edge, maya_source=spec['name']))
        if 1-edge < .00001:
            continue
        weight = (1-edge)/6
        for i in range(6):
            # Sampling at the edge (value=0 for large exponents) used to
            # produce a 180-degree helper, spilling volumetric light sideways.
            # Interior levels bound each transition to its actual angular band.
            low = edge + (i+.25)*weight
            high = min(1, edge + (i+.75)*weight)
            outer = min(inner, 2*math.acos(math.exp(math.log(low)/dropoff)))
            inner_angle = min(outer, 2*math.acos(math.exp(math.log(high)/dropoff)))
            result.append(dict(spec, name=spec['name']+'::EeveeDropoff'+str(i), maya_source=spec['name'],
                               intensity=spec['intensity']*weight, cone_angle=outer,
                               penumbra=(inner_angle-outer)*.5, dropoff=0))
    return result
