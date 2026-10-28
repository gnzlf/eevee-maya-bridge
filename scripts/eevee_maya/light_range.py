"""Keep local-light influence outside receivers without changing brightness."""
import math


def influence_distance(origin, bounds, reference=5.0, volume_distance=0.0):
    extent=0.0
    for low,high in bounds:
        extent=max(extent,math.sqrt(sum(max(abs(a-p),abs(b-p))**2 for a,b,p in zip(low,high,origin))))
    # Keep the fade outside visible receivers, without a huge energy-dependent
    # radius that degrades the near/far precision of punctual shadow maps.
    return max(1.0,4*extent,4*reference,4*volume_distance)
