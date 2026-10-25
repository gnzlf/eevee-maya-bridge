"""Windows shared-memory color/depth frame, protected by a named mutex."""
import ctypes
from ctypes import wintypes
import mmap
import struct
import json
import pickle

MAX_PIXELS = 1920 * 1920
HEADER = struct.Struct("<QIIIId")
OFFSET = 64
CAPACITY = OFFSET + MAX_PIXELS * 20


class SharedFrame:
    def __init__(self, identifier):
        self.identifier = identifier
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.mutex = self.kernel.CreateMutexW(None, False, "Local\\EeveeMayaMutex_" + identifier)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.memory = mmap.mmap(-1, CAPACITY, tagname="Local\\EeveeMayaFrame_" + identifier)

    def write(self, frame_id, width, height, color, depth, seconds):
        if width * height > MAX_PIXELS:
            raise ValueError("Frame exceeds shared-memory capacity")
        color, depth = memoryview(color).cast("B"), memoryview(depth).cast("B")
        if len(color) != width * height * 16 or len(depth) != width * height * 4:
            raise ValueError("Expected RGBA float32 and depth float32")
        if self.kernel.WaitForSingleObject(self.mutex, 1000) not in (0, 0x80):
            raise TimeoutError("Shared frame locked")
        try:
            self.memory[OFFSET:OFFSET + len(color)] = color
            self.memory[OFFSET + len(color):OFFSET + len(color) + len(depth)] = depth
            HEADER.pack_into(self.memory, 0, frame_id, width, height, len(color), len(depth), seconds)
        finally:
            self.kernel.ReleaseMutex(self.mutex)

    def read(self, previous_id=0):
        if self.kernel.WaitForSingleObject(self.mutex, 0) not in (0, 0x80):
            return None
        try:
            frame_id, width, height, color_bytes, depth_bytes, seconds = HEADER.unpack_from(self.memory)
            if frame_id <= previous_id:
                return None
            if not (0 < width * height <= MAX_PIXELS and color_bytes == width * height * 16
                    and depth_bytes == width * height * 4):
                raise ValueError("Invalid shared frame header")
            return {"id": frame_id, "width": width, "height": height, "seconds": seconds,
                    "color": self.memory[OFFSET:OFFSET + color_bytes],
                    "depth": self.memory[OFFSET + color_bytes:OFFSET + color_bytes + depth_bytes]}
        finally:
            self.kernel.ReleaseMutex(self.mutex)

    def close(self):
        if self.memory:
            self.memory.close()
            self.memory = None
        if self.mutex:
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None

    @property
    def presented_id(self):
        return struct.unpack_from("<Q", self.memory, 40)[0]

    def acknowledge(self, frame_id):
        # Highest frame no longer sampled by Maya, NOT the currently displayed
        # frame. Releasing that frame early allows the producer to overwrite it.
        struct.pack_into("<Q", self.memory, 40, max(self.presented_id, frame_id))


class SharedMailbox:
    """Latest-value scene/metadata channel with no file-open race or disk writes."""
    HEADER = struct.Struct("<QI")

    def __init__(self, identifier, channel, capacity):
        # Reuse the Win32 lifetime/locking setup without allocating a frame.
        self.capacity = capacity
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        suffix = identifier + "_" + channel
        self.mutex = self.kernel.CreateMutexW(None, False, "Local\\EeveeMailboxMutex_" + suffix)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.memory = mmap.mmap(-1, capacity + OFFSET, tagname="Local\\EeveeMailbox_" + suffix)

    def write(self, token, value):
        # Private, per-session, same-user IPC only. Never deserialize external files here.
        payload = pickle.dumps(value, protocol=4)
        if len(payload) > self.capacity:
            raise ValueError("Scene exceeds shared mailbox capacity: %d bytes" % self.capacity)
        if self.kernel.WaitForSingleObject(self.mutex, 1000) not in (0, 0x80):
            raise TimeoutError("Mailbox locked")
        try:
            self.memory[OFFSET:OFFSET + len(payload)] = payload
            self.HEADER.pack_into(self.memory, 0, token, len(payload))
        finally:
            self.kernel.ReleaseMutex(self.mutex)

    def read(self, previous_id=0):
        if self.kernel.WaitForSingleObject(self.mutex, 0) not in (0, 0x80):
            return None
        try:
            token, length = self.HEADER.unpack_from(self.memory)
            if token <= previous_id:
                return None
            if not (0 < length <= self.capacity):
                raise ValueError("Invalid mailbox payload size")
            payload = self.memory[OFFSET:OFFSET + length]
            struct.pack_into("<Q", self.memory, 16, token)
        finally:
            self.kernel.ReleaseMutex(self.mutex)
        return pickle.loads(payload)

    @property
    def consumed_id(self):
        return struct.unpack_from("<Q", self.memory, 16)[0]

    close = SharedFrame.close
