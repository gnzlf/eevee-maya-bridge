"""Eevee virtual shadow quality, independent of the panel's output resolution."""
PRESETS = {
    'low': (0.25, 1, 4, '128'),
    'medium': (0.5, 1, 6, '256'),
    'high': (1.0, 2, 8, '512'),
    'ultra': (1.0, 4, 16, '1024'),
}
LABELS = (('Baja · 25%', 'low'), ('Media · 50%', 'medium'),
          ('Alta · 100%', 'high'), ('Ultra · 100% + mejores sombras suaves', 'ultra'))
POOLS = ('128', '256', '512', '1024', '1536', '2048')
PREFERENCES = {'shadow_quality': 'eeveeShadowQuality', 'shadow_pool_size': 'eeveeShadowPoolSize'}


def resolve(config):
    """Validate persisted preferences before passing them to Blender RNA."""
    preset = config.get('shadow_quality', 'high')
    if preset not in PRESETS:
        preset = 'high'
    resolution, rays, steps, default_pool = PRESETS[preset]
    pool = str(config.get('shadow_pool_size', 'auto'))
    if pool not in POOLS:
        pool = default_pool
    return {'preset': preset, 'resolution': resolution, 'rays': rays,
            'steps': steps, 'pool': pool}


def apply(eevee, config):
    values = resolve(config)
    # Avoid invalidating Eevee's shadow resources on every unchanged frame.
    for attribute, key in (('shadow_resolution_scale', 'resolution'), ('shadow_pool_size', 'pool'),
                           ('shadow_ray_count', 'rays'), ('shadow_step_count', 'steps')):
        if getattr(eevee, attribute) != values[key]:
            setattr(eevee, attribute, values[key])
    return values
