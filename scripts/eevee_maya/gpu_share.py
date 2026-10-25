"""ctypes interface to our D3D11/WGL texture sharing library, with no Maya dependency."""
import ctypes
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_dll = None


def library():
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(str(ROOT / "bin" / "eevee_gpu_v5.dll"))
        _dll.eb_context.restype = ctypes.c_uint64
        _dll.eb_error.restype = ctypes.c_char_p
        _dll.eb_clip_mask.restype = ctypes.c_uint
        _dll.eb_create.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.POINTER(ctypes.c_uint64)]
        _dll.eb_create.restype = ctypes.c_void_p
        _dll.eb_handle.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _dll.eb_handle.restype = ctypes.c_uint64
        _dll.eb_destroy.argtypes = [ctypes.c_void_p]
        _dll.eb_publish.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _dll.eb_draw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
    return _dll


class GpuShare:
    @staticmethod
    def current_context():
        return library().eb_context()

    def __init__(self, identifier, width, height, handles=None):
        self.dll = library()
        source = (ctypes.c_uint64 * 2)(*handles) if handles else None
        self.pointer = self.dll.eb_create("Local\\EeveeGpu_" + identifier, width, height, source)
        if not self.pointer:
            raise RuntimeError(self.dll.eb_error().decode("utf-8", "replace"))
        self.width, self.height = width, height
        self.handles = [self.dll.eb_handle(self.pointer, i) for i in range(2)]

    def publish(self, channel):
        if not self.dll.eb_publish(self.pointer, channel):
            raise RuntimeError(self.dll.eb_error().decode("utf-8", "replace"))

    def draw(self, frame):
        effects, cam = frame.get("effects", {}), frame.get("camera", {})
        native=frame.get("native") or {}
        values = (ctypes.c_float * 19)(
            bool(effects.get("bloom")), effects.get("bloom_threshold", .8),
            effects.get("bloom_strength", .5), bool(cam.get("dof") and not cam.get("orthographic")),
            cam.get("focus_distance", 10), cam.get("focal_length", 35) * .1,
            cam.get("fstop", 5.6), cam.get("sensor_width_cm", 3.6),
            cam.get("near", .1), cam.get("far", 10000), max(.001,cam.get("focus_region_scale",1)),
            bool(native.get("ao")),native.get("ao_radius_pixels",16)/max(1,native.get("viewport_width",self.width)),
            max(0,native.get("ao_amount",1)),math.tan(cam.get("fov_x",.8)*.5),
            bool(cam.get("orthographic")),cam.get("ortho_width",10),cam.get("shift_x",0),cam.get("shift_y",0))
        if not self.dll.eb_draw(self.pointer, values):
            raise RuntimeError(self.dll.eb_error().decode("utf-8", "replace"))

    def close(self):
        if self.pointer:
            self.dll.eb_destroy(self.pointer)
            self.pointer = None
