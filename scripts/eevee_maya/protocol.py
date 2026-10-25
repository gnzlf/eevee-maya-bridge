"""File mailbox, shared by Maya and Blender without third party packages."""
import json
import os
from pathlib import Path
import time


def read_json(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, separators=(",", ":"), allow_nan=False)
    # Windows readers briefly hold a file handle without FILE_SHARE_DELETE.
    # Retry the atomic rename; never expose partially written scene JSON.
    for attempt in range(20):
        try:
            os.replace(str(temporary), str(path))
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)
