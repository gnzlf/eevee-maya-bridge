"""Map Maya's common scene-linear spaces and display views to Blender 5.2."""
def image_space(source, noncolor=False):
    if noncolor or source.lower() in ('raw', 'non-color', 'utility - raw'):
        return 'Non-Color'
    return {'scene-linear Rec.709-sRGB': 'Linear Rec.709',
            'Utility - Linear - sRGB': 'Linear Rec.709',
            'scene-linear Rec.2020': 'Linear Rec.2020',
            'Utility - sRGB - Texture': 'sRGB'}.get(source, source or 'sRGB')


def resolve(source):
    source = source or {}
    space = source.get('rendering_space', 'Linear Rec.709')
    normalized = ''.join(c for c in space.lower() if c.isalnum())
    if normalized == 'acescg':
        working = 'ACEScg'
    elif normalized in ('linearrec2020', 'scenelinearrec2020'):
        working = 'Linear Rec.2020'
    else:
        working = 'Linear Rec.709'
    view = source.get('view', '')
    if not source:
        display_view = 'AgX'
    elif not source.get('enabled', True) or view.lower() == 'raw':
        display_view = 'Raw'
    elif view.startswith(('ACES 1.', 'ACES 1 ')):
        display_view = 'ACES 1.3'
    elif view.startswith('ACES 2.'):
        display_view = 'ACES 2.0'
    elif view.startswith('Un-tone-mapped'):
        display_view = 'Standard'
    else:
        display_view = 'AgX'
    return {'working_space': working, 'view': display_view,
            'source_space': space, 'source_view': view,
            'view_approximation': display_view not in ('Raw', 'Standard')}
