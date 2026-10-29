"""Reuse Maya OCIO when available; retain the legacy mapping as a fallback."""
import json
import os
from pathlib import Path
import re


def prepare_native(source, directory):
    """Create a session-local config. Never alter Maya's config or its LUTs.

    Blender obtains its working space from the scene_linear role at startup.
    Keep LUT paths anchored to the original config, including relative ctfs.
    """
    source = source or {}
    path = Path(source.get('config_path') or '')
    if not path.is_file() or not source.get('native_ocio', False):
        return None
    text = path.read_text(encoding='utf-8-sig')
    space = source.get('rendering_space', 'ACEScg')
    if not re.search(r'^  scene_linear:.*$', text, re.M):
        return None
    text = re.sub(r'^  scene_linear:.*$', '  scene_linear: '+json.dumps(space), text, flags=re.M)
    match = re.search(r'^search_path:[ \t]*(.*)$', text, re.M)
    if not match:
        return None
    value = match.group(1).strip().strip('"\'')
    # Only scalar search paths are rewritten. Exotic custom configurations
    # retain the established Blender fallback rather than being guessed.
    if value.startswith('['):
        return None
    paths = [str(path.parent / item).replace('\\', '/') if not os.path.isabs(item) else item
             for item in value.split(os.pathsep) if item]
    paths.append(path.parent.as_posix())
    # A YAML sequence is unambiguous for Windows absolute paths.
    text = text[:match.start()]+'search_path: '+json.dumps(paths)+text[match.end():]
    target = Path(directory)/'maya-color.ocio'
    target.write_text(text, encoding='utf-8')
    return target
def image_space(source, noncolor=False):
    if os.environ.get('EEVEE_NATIVE_OCIO') == '1':
        return 'Raw' if noncolor else (source or 'sRGB')
    if noncolor or source.lower() in ('raw', 'non-color', 'utility - raw'):
        return 'Non-Color'
    return {'scene-linear Rec.709-sRGB': 'Linear Rec.709',
            'Utility - Linear - sRGB': 'Linear Rec.709',
            'scene-linear Rec.2020': 'Linear Rec.2020',
            'Utility - sRGB - Texture': 'sRGB'}.get(source, source or 'sRGB')


def resolve(source):
    source = source or {}
    if os.environ.get('EEVEE_NATIVE_OCIO') == '1':
        return {'working_space': source.get('rendering_space', 'ACEScg'),
                'view': source.get('native_view') or source.get('view', '').split(' (')[0],
                'display': source.get('display', 'sRGB'),
                'source_space': source.get('rendering_space'), 'source_view': source.get('view'),
                'view_approximation': False, 'native_ocio': True}
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
