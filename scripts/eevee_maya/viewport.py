"""Viewport 2.0 override: Eevee color, Maya editing overlays, present."""
import maya.api.OpenMayaRender as render
from pathlib import Path
import ctypes
import time
import math
from collections import deque

ROOT = Path(__file__).resolve().parents[2]

NAME = "EeveeBridge"
_override = None


class CameraSync(render.MUserRenderOperation):
    """Read VP2's actual projection for this draw, including playblast targets."""
    def __init__(self, owner):
        super().__init__('EeveeNativeCameraSync')
        self.owner = owner

    def execute(self, context):
        from . import ui, capture
        controller = ui._controller
        if controller is None or controller.panel != self.owner.destination:
            return
        path = context.getCurrentCameraPath()
        frame = {'path': path.fullPathName(), 'matrix': list(path.inclusiveMatrix()),
                 'projection': list(context.getMatrix(render.MFrameContext.kProjectionMtx)),
                 'view': list(context.getMatrix(render.MFrameContext.kViewMtx)),
                 'size': list(context.getViewportDimensions()[2:])}
        controller.viewport_camera = frame
        if capture.active():
            controller.before_draw(frame)
        else:
            controller.tick(refresh=False)


class CaptureGuard(render.MUserRenderOperation):
    """Mark late capture errors after the queued image/UI operations finish."""
    def __init__(self):
        super().__init__('EeveeCaptureGuard')

    def execute(self, context):
        from . import ui, capture
        if not capture.active() or ui._controller is None or not ui._controller.capture_error:
            return
        # Maya can prepare the operation list before CameraSync runs, so a
        # late timeout cannot be handled by changing that list. Clear the bound
        # OpenGL capture target here, preserving its caller's clear/write state.
        gl=ctypes.WinDLL('opengl32')
        gl.glClearColor.argtypes=[ctypes.c_float]*4
        gl.glColorMask.argtypes=[ctypes.c_ubyte]*4
        gl.glIsEnabled.restype=ctypes.c_ubyte
        color=(ctypes.c_float*4)();mask=(ctypes.c_ubyte*4)()
        gl.glGetFloatv(0x0C22,color);gl.glGetBooleanv(0x0C23,mask)
        scissor=gl.glIsEnabled(0x0C11)
        try:
            gl.glDisable(0x0C11);gl.glColorMask(1,1,1,1)
            gl.glClearColor(.7,0,0,1);gl.glClear(0x00004000)
        finally:
            gl.glClearColor(*color);gl.glColorMask(*mask)
            if scissor:gl.glEnable(0x0C11)


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


class CaptureFailure(render.MSceneRender):
    """An explicit failure image must never look like a valid older pose."""
    def __init__(self):
        super().__init__('EeveeCaptureFailure')

    def renderFilterOverride(self):
        return 0

    def clearOperation(self):
        operation = super().clearOperation()
        operation.setMask(render.MClearOperation.kClearAll)
        operation.setClearColor((.7, 0, 0, 1))
        return operation


class LoadingBackground(CaptureFailure):
    def __init__(self):
        render.MSceneRender.__init__(self, 'EeveeStartupBackground')

    def renderFilterOverride(self):
        return render.MSceneRender.kRenderUIItems

    def clearOperation(self):
        operation = super().clearOperation()
        operation.setClearColor((.035, .04, .05, 1))
        return operation


class GraphicsNotice(render.MHUDRender):
    """Native, API-independent notice; DirectX never reaches the GL bridge."""
    def __init__(self):
        super().__init__()
        self.draws = 0

    def execute(self, context):
        pass

    def hasUIDrawables(self):
        return True

    def addUIDrawables(self, draw, context):
        import maya.api.OpenMaya as om
        _, _, width, height = context.getViewportDimensions()
        x, y = width * .5, height * .5
        draw.beginDrawable(render.MUIDrawManager.kNonSelectable)
        draw.setColor(om.MColor((.95, .75, .3, 1)))
        draw.setFontSize(20)
        draw.text2d(om.MPoint(x, y + 35), 'Eevee necesita OpenGL Core Profile', render.MUIDrawManager.kCenter)
        draw.setColor(om.MColor((.92, .94, .98, 1)))
        draw.setFontSize(12)
        draw.text2d(om.MPoint(x, y + 5), 'Maya está usando DirectX 11.', render.MUIDrawManager.kCenter)
        draw.text2d(om.MPoint(x, y - 20), 'Abre el cuadradito junto a Renderer > Eevee para configurar OpenGL.', render.MUIDrawManager.kCenter)
        draw.text2d(om.MPoint(x, y - 45), 'Guarda tu trabajo y reinicia Maya después del cambio.', render.MUIDrawManager.kCenter)
        draw.text2d(om.MPoint(x, y - 80), 'Renderer > Viewport 2.0 para volver', render.MUIDrawManager.kCenter)
        draw.endDrawable()
        self.draws += 1


class Loading(render.MHUDRender):
    def __init__(self):
        super().__init__()
        self.draws = 0
        self.last_status = {}

    def execute(self, context):
        pass

    def hasUIDrawables(self):
        return True

    def addUIDrawables(self, draw, context):
        from . import ui, startup
        import maya.api.OpenMaya as om
        controller = ui._controller
        progress, elapsed, error = {'stage':'starting'}, 0, None
        if controller:
            engine = controller.engine
            progress = engine.startup_progress()
            elapsed = max(0, time.monotonic() - engine.started)
            error = (controller.startup_error or engine.last_response.get('error')
                     or controller.engine.frame is not None and _override.gpu_image.error)
            if engine.process is not None and engine.process.poll() is not None:
                error = 'El motor se cerró. Consulta el Script Editor y el registro de Eevee.'
        _, _, width, height = context.getViewportDimensions()
        x, y = width*.5, height*.5
        phase = int(time.monotonic()*16) % 12
        draw.beginDrawable(render.MUIDrawManager.kNonSelectable)
        draw.setLineWidth(3)
        for index in range(12):
            angle = index*math.pi/6
            alpha = .15 + .85*((index-phase) % 12)/11
            draw.setColor(om.MColor((.95,.3,.25,1) if error else (.25,.65,1,alpha)))
            draw.line2d(om.MPoint(x+math.cos(angle)*19,y+55+math.sin(angle)*19),
                        om.MPoint(x+math.cos(angle)*29,y+55+math.sin(angle)*29))
        draw.setColor(om.MColor((.92,.94,.98,1)));draw.setFontSize(20)
        draw.text2d(om.MPoint(x,y+3),'Eevee',render.MUIDrawManager.kCenter)
        draw.setFontSize(13)
        text = 'No se pudo iniciar Eevee' if error else startup.label(progress)
        draw.text2d(om.MPoint(x,y-25),text,render.MUIDrawManager.kCenter,dynamic=True)
        draw.setFontSize(11);draw.setColor(om.MColor((.65,.69,.75,1)))
        detail = str(error).splitlines()[-1][:max(24,min(160,int(width/7)))] if error else '%.0f s transcurridos' % elapsed
        draw.text2d(om.MPoint(x,y-49),detail,render.MUIDrawManager.kCenter,dynamic=True)
        draw.text2d(om.MPoint(x,y-78),'Renderer > Viewport 2.0 para salir',render.MUIDrawManager.kCenter)
        draw.endDrawable()
        self.draws += 1
        self.last_status = {'label':text,'phase':phase,'elapsed':elapsed,'error':bool(error),
                            'viewport':[width,height]}


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
        self.capture_failure = CaptureFailure()
        self.loading_background = LoadingBackground()
        self.loading = Loading()
        self.graphics_notice = GraphicsNotice()
        self.camera_sync = CameraSync(self)
        self.capture_guard = CaptureGuard()
        self.operations = []
        self.index = 0
        self.has_image = False
        self.destination = None
        self.pending_attach = False

    def uiName(self):
        return "Eevee"

    def supportedDrawAPIs(self):
        # DX support is ONLY the native compatibility notice. Shared textures
        # and Eevee drawing remain OpenGL-only and are guarded in setup().
        return render.MRenderer.kOpenGL | render.MRenderer.kOpenGLCoreProfile | render.MRenderer.kDirectX11

    def setup(self, destination):
        self.destination = destination
        from . import ui, capture
        if render.MRenderer.drawAPI() == render.MRenderer.kDirectX11:
            self.operations = ([self.capture_failure, self.present] if capture.active()
                               else [self.loading_background, self.graphics_notice, self.present])
            return
        if capture.active() and ui._controller is not None and ui._controller.capture_error:
            self.operations = [self.capture_failure, self.present]
            return
        if not capture.active() and (ui._controller is None or ui._controller.panel != destination):
            # Maya's Renderer menu assigns an override directly, without going
            # through our menu command. Start its controller on the next idle.
            self.has_image = False
            if not self.pending_attach:
                import maya.cmds as cmds
                self.pending_attach = True
                def attach_selected_panel():
                    try:
                        if (_override is self and cmds.modelPanel(destination, exists=True) and
                                cmds.modelEditor(destination, query=True, rendererOverrideName=True) == NAME and
                                (ui._controller is None or ui._controller.panel != destination)):
                            ui.attach(destination)
                    finally:
                        self.pending_attach = False
                cmds.evalDeferred(attach_selected_panel)
        controller = ui._controller
        if capture.active() and controller is not None:
            image = self.gpu_image if controller.engine.gpu else self.quad
            self.operations = [self.camera_sync, image, self.overlay, self.capture_guard, self.present]
            return
        if (not capture.active() and controller is not None and controller.panel == destination
                and not controller.presented_once and (controller.startup_error or self.gpu_image.error)):
            self.operations = [self.camera_sync, self.loading_background, self.loading, self.present]
            return
        image = self.gpu_image if self.gpu_image.frame else self.quad
        self.operations = ([image, self.overlay, self.present] if self.has_image
                           else [self.loading_background, self.loading, self.present])
        if not self.has_image and controller is not None and controller.presented_once:
            self.operations = [self.fallback, self.present]
        if (self.has_image or controller is not None and controller.presented_once) and self.native.get("displayAppearance") in ("wireframe", "points", "boundingBox"):
            self.operations = [self.fallback, self.present]
        elif self.has_image and self.native.get("wireframeOnShaded"):
            self.operations = [image, self.wire_overlay, self.overlay, self.present]
        self.operations.insert(0, self.camera_sync)

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
    existing = render.MRenderer.findRenderOverride(NAME)
    if _override is not None and existing is not None:
        return _override
    if existing is not None:
        raise RuntimeError("Eevee ya tiene un viewport registrado por otra instancia. Reinicia Maya para cargar una sola versión del puente.")
    candidate = _override if _override is not None else Override()
    try:
        render.MRenderer.registerOverride(candidate)
    except RuntimeError as exc:
        raise RuntimeError("No se pudo registrar el viewport Eevee en Viewport 2.0. Comprueba Preferences > Display > Rendering engine (OpenGL Core Profile) y reinicia Maya. Detalle: " + str(exc)) from exc
    _override = candidate
    return _override


def deregister():
    global _override
    if _override is not None:
        # Maya can already have removed the override after a failed load or
        # during shutdown; deregistering a missing override raises kFailure.
        if render.MRenderer.findRenderOverride(NAME) is not None:
            render.MRenderer.deregisterOverride(_override)
        try:
            _override.quad.release()
        finally:
            try:
                _override.gpu_image.release()
            finally:
                _override = None
