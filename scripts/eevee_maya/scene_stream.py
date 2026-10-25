"""Binary mesh deltas from Maya's evaluated output, extracted with the Maya C++ API."""
import ctypes
from pathlib import Path

_dll = None


def library():
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(str(Path(__file__).resolve().parents[2] / "bin" / "eevee_scene.dll"))
        _dll.es_error.restype = ctypes.c_char_p
        _dll.es_create.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint32]
        _dll.es_create.restype = ctypes.c_void_p
        _dll.es_update.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint64)]
        _dll.es_update.restype = ctypes.c_void_p
        _dll.es_destroy.argtypes = [ctypes.c_void_p]
    return _dll


class SceneStream:
    def __init__(self, names):
        self.names = list(names)
        self.dll = library()
        paths = (ctypes.c_char_p * len(names))(*(n.encode("utf-8") for n in names))
        self.pointer = self.dll.es_create(paths, len(names))
        if not self.pointer:
            raise RuntimeError(self.dll.es_error().decode("utf-8", "replace"))

    def update(self, initial=False):
        length = ctypes.c_uint64()
        pointer = self.dll.es_update(self.pointer, initial, ctypes.byref(length))
        if not pointer:
            raise RuntimeError(self.dll.es_error().decode("utf-8", "replace"))
        return ctypes.string_at(pointer, length.value)

    def close(self):
        if self.pointer:
            self.dll.es_destroy(self.pointer)
            self.pointer = None
