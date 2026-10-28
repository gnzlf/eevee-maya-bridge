"""Resolve an existing image or concrete UDIM tiles without changing Maya nodes."""
import os
from pathlib import Path
import re


def resolve(path, tiled=False, pattern=''):
    if not path:
        return None
    if tiled:
        if '<UDIM>' not in pattern:
            pattern = path if '<UDIM>' in path else re.sub(r'(?<!\d)1\d{3}(?=\.[^.]+$)', '<UDIM>', path)
        if '<UDIM>' in pattern:
            template = Path(pattern)
            expression = re.compile(re.escape(template.name).replace(re.escape('<UDIM>'), r'(1\d{3})'), re.IGNORECASE)
            try:
                tiles = sorted((int(match.group(1)), entry.path)
                               for entry in os.scandir(template.parent)
                               for match in [expression.fullmatch(entry.name)]
                               if match and entry.is_file())
            except OSError:
                return None
            if not tiles:
                return None
            return {'path': tiles[0][1], 'udim_pattern': pattern, 'tiles': [number for number, _ in tiles]}
    return {'path': path} if os.path.isfile(path) else None
