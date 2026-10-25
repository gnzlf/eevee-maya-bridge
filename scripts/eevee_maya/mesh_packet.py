"""Versioned, bounds-checked binary mesh updates, shared by Maya and Blender."""
import struct

HEADER = struct.Struct("<IIIII")


def records(payload):
    view = memoryview(payload)
    if len(view) < 4:
        raise ValueError("Truncated mesh packet")
    count = struct.unpack_from("<I", view)[0]
    offset = 4
    for _ in range(count):
        if offset + HEADER.size > len(view):
            raise ValueError("Truncated mesh record")
        index, flags, vertices, loops, visible = HEADER.unpack_from(view, offset)
        offset += HEADER.size
        if flags & ~23:
            raise ValueError("Unsupported mesh packet flags")
        result = {"index": index, "flags": flags, "visible": bool(visible)}
        for name, length in (("matrix", 128 if flags & 1 else 0),
                             ("points", vertices * 12 if flags & 2 else 0),
                             ("normals", loops * 12 if flags & 4 else 0)):
            if offset + length > len(view):
                raise ValueError("Truncated " + name)
            if length:
                result[name] = view[offset:offset + length]
            offset += length
        yield result
    if offset != len(view):
        raise ValueError("Unexpected mesh packet bytes")
