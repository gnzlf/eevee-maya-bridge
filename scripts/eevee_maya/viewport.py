"""Viewport 2.0 override: Eevee color, Maya editing overlays, present."""
import maya.api.OpenMayaRender as render
from pathlib import Path
import ctypes
import time
from collections import deque

ROOT = Path(__file__).resolve().parents[2]

NAME = "EeveeBridge"
_override = None


class GPUImage(render.MUserRenderOperation):
    """Draw our shared textures in Maya's supplied GL context, preserving its state."""
    def __init__(self):
        super().__init__("EeveeGPUImage")
        self.frame = None
        self.receiver = None
        self.key = None
        self.generation = None
        self.receivers = {}
        self.displayed_id = 0
        self.draws = 0
        self.draw_ms = 0
        self.error = None
        self.presentations = deque(maxlen=4096)

    def execute(self, context):
        if not self.frame:
            return
        try:
            from .gpu_share import GpuShare
            frame = self.frame
            key = (GpuShare.current_context(), frame["gpu_session"], frame["width"], frame["height"], tuple(frame["gpu_handles"]))
            generation = frame.get("gpu_generation", frame["gpu_session"])
            if self.generation != generation:
                for receiver in self.receivers.values():
                    receiver.close()
                self.receivers = {}
                self.generation = generation
                self.key = None
            if self.key != key:
                if key not in self.receivers:
                    self.receivers[key] = GpuShare(frame["gpu_session"], frame["width"], frame["height"], frame["gpu_handles"])
                self.receiver = self.receivers[key]
                self.key = key
            started = time.perf_counter()
            self.receiver.draw(frame)
            self.draw_ms = (time.perf_counter()-started)*1000
            if self.displayed_id != frame["id"]:
                self.presentations.append((time.perf_counter(), frame["id"], frame.get("maya_frame")))
            self.displayed_id = frame["id"]
            self.draws += 1
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            raise

    def release(self):
        for receiver in self.receivers.values():
            receiver.close()
        self.receivers = {}
        self.receiver = None
        self.generation = None
        self.frame = None
        self.key = None
        self.displayed_id = 0


class ImageQuad(render.MQuadRender):
    def __init__(self):
        super().__init__("EeveeImage")
        self.effect = None
        self.texture = None
        self.filepath = None
        self.frame = None
        self.depth_texture = None
        self.dimensions = None
        self.depth_state = None

    def shader(self):
        if self.effect is None:
            manager = render.MRenderer.getShaderManager()
            manager.addShaderPath(str(ROOT / "shaders"))
            self.effect = manager.getEffectsFileShader("EeveeBlit", "", None, False)
            self.effect.setParameter("flipVertical", True)
            self.effect.setParameter("hasDepth", False)
        if self.frame:
            manager = render.MRenderer.getTextureManager()
            width, height = self.frame["width"], self.frame["height"]
            recreate = self.dimensions != (width, height)
            for attribute, parameter, payload, format_, bytes_per_pixel in (
                ("texture", "bridgeColor", "color", render.MRenderer.kR32G32B32A32_FLOAT, 16),
                ("depth_texture", "bridgeDepth", "depth", render.MRenderer.kR32_FLOAT, 4)):
                current = getattr(self, attribute)
                buffer = ctypes.create_string_buffer(self.frame[payload])
                pointer = ctypes.addressof(buffer)
                if recreate or current is None:
                    desc = render.MTextureDescription()
                    desc.setToDefault2DTexture()
                    desc.fWidth, desc.fHeight = width, height
                    desc.fBytesPerRow = width * bytes_per_pixel
                    desc.fBytesPerSlice = width * height * bytes_per_pixel
                    desc.fFormat = format_
                    desc.fMipmaps = 1
                    texture = manager.acquireTexture("", desc, pointer, False)
                    if current:
                        manager.releaseTexture(current)
                    setattr(self, attribute, texture)
                    assignment = render.MTextureAssignment()
                    assignment.texture = texture
                    self.effect.setParameter(parameter, assignment)
                else:
                    current.update(pointer, False, width * bytes_per_pixel)
            self.dimensions = (width, height)
            self.effect.setParameter("flipVertical", True)
            self.effect.setParameter("hasDepth", True)
            effects = self.frame.get("effects", {})
            self.effect.setParameter("screenBloom", bool(effects.get("bloom", False)))
            self.effect.setParameter("bloomThreshold", float(effects.get("bloom_threshold", 0.8)))
            self.effect.setParameter("bloomStrength", float(effects.get("bloom_strength", 0.5)))
            self.effect.setParameter("pixelSize", (1.0 / width, 1.0 / height))
            camera = self.frame.get("camera", {})
            self.effect.setParameter("previewDof", bool(camera.get("dof", False) and not camera.get("orthographic", False)))
            self.effect.setParameter("focusRegionScale",float(camera.get("focus_region_scale",1)))
            for name, value in (("focusDistance", camera.get("focus_distance", 10)),
                                ("focalLengthCM", camera.get("focal_length", 35) * 0.1),
                                ("cameraFstop", camera.get("fstop", 5.6)),
                                ("sensorWidthCM", camera.get("sensor_width_cm", 3.6)),
                                ("nearClip", camera.get("near", 0.1)),
                                ("farClip", camera.get("far", 10000))):
                self.effect.setParameter(name, float(value))
            self.frame = None
        if self.filepath:
            manager = render.MRenderer.getTextureManager()
            texture = manager.acquireTexture(str(self.filepath), "", 1)
            if texture:
                assignment = render.MTextureAssignment()
                assignment.texture = texture
                self.effect.setParameter("bridgeColor", assignment)
                if self.texture:
                    manager.releaseTexture(self.texture)
                self.texture = texture
                self.filepath = None
        return self.effect

    def depthStencilStateOverride(self):
        if self.depth_state is None:
            desc = render.MDepthStencilStateDesc()
            desc.depthEnable = True
            desc.depthWriteEnable = True
            desc.depthFunc = render.MStateManager.kCompareAlways
            self.depth_state = render.MStateManager.acquireDepthStencilState(desc)
        return self.depth_state

    def clearOperation(self):
        operation = super().clearOperation()
        operation.setMask(render.MClearOperation.kClearAll)
        operation.setClearColor((0.06, 0.06, 0.06, 1.0))
        return operation

    def enableSRGBWrite(self):
        return False

    def release(self):
        if self.texture:
            render.MRenderer.getTextureManager().releaseTexture(self.texture)
            self.texture = None
        if self.depth_texture:
            render.MRenderer.getTextureManager().releaseTexture(self.depth_texture)
            self.depth_texture = None
        if self.depth_state:
            render.MStateManager.releaseDepthStencilState(self.depth_state)
            self.depth_state = None
        if self.effect:
            render.MRenderer.getShaderManager().releaseShader(self.effect)
            self.effect = None


class Overlays(render.MSceneRender):
    def __init__(self):
        super().__init__("EeveeMayaOverlays")

    def renderFilterOverride(self):
        return render.MSceneRender.kRenderUIItems

    def postEffectsOverride(self):
        # UI-only rendering must not apply VP2's DOF/AO again to Eevee color.
        return render.MSceneRender.kPostEffectDisableAll

    def clearOperation(self):
        operation = super().clearOperation()
        operation.setMask(render.MClearOperation.kClearNone)
        return operation


class WireOverlay(Overlays):
    def __init__(self):
        render.MSceneRender.__init__(self, "EeveeMayaWireOverlay")

    def renderFilterOverride(self):
        return render.MSceneRender.kRenderOpaqueShadedItems | render.MSceneRender.kRenderTransparentShadedItems

    def displayModeOverride(self):
        return render.MSceneRender.kWireFrame


class Override(render.MRenderOverride):
    def __init__(self):
        super().__init__(NAME)
        self.quad = ImageQuad()
        self.gpu_image = GPUImage()
        self.fallback = render.MSceneRender("EeveeWaiting")
        self.overlay = Overlays()
        self.wire_overlay = WireOverlay()
        self.native = {}
        self.present = render.MPresentTarget("EeveePresent")
        self.operations = []
        self.index = 0
        self.has_image = False
        self.destination = None

    def uiName(self):
        return "Eevee (Blender Bridge)"

    def supportedDrawAPIs(self):
        # Copy.ogsfx ships with Maya and runs on its OpenGL renderer.
        return render.MRenderer.kOpenGL | render.MRenderer.kOpenGLCoreProfile

    def setup(self, destination):
        self.destination = destination
        image = self.gpu_image if self.gpu_image.frame else self.quad
        self.operations = ([image, self.overlay, self.present] if self.has_image
                           else [self.fallback, self.present])
        if self.native.get("displayAppearance") in ("wireframe", "points", "boundingBox"):
            self.operations = [self.fallback, self.present]
        elif self.has_image and self.native.get("wireframeOnShaded"):
            self.operations = [image, self.wire_overlay, self.overlay, self.present]

    def cleanup(self):
        pass

    def startOperationIterator(self):
        self.index = 0
        return True

    def renderOperation(self):
        if self.index < len(self.operations):
            return self.operations[self.index]
        return None

    def nextRenderOperation(self):
        self.index += 1
        return self.index < len(self.operations)

    def set_image(self, path):
        self.quad.filepath = path
        self.has_image = True

    def set_frame(self, frame):
        if "gpu_handles" in frame:
            self.gpu_image.frame = frame
        else:
            self.gpu_image.frame = None
            self.quad.frame = frame
        self.has_image = True


def register():
    global _override
    if _override is None:
        _override = Override()
        render.MRenderer.registerOverride(_override)
    return _override


def deregister():
    global _override
    if _override:
        render.MRenderer.deregisterOverride(_override)
        _override.quad.release()
        _override.gpu_image.release()
        _override = None
