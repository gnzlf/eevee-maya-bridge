"""Maya modelPanel controls and main-thread scene sampling."""
import atexit
import traceback
import time

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as render
import maya.api.OpenMaya as om

try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

from . import exporter, viewport, native_controls, capture
from .engine import Engine, ROOT, settings
from .protocol import write_json
from .changes import SceneChanges
from .scene_stream import SceneStream
from .light_links import LightLinks
from .quality import InteractionQuality
from .mesh_packet import records

WINDOW = "eeveeBridgeWindow"
MENU = "eeveeBridgeMenu"
_controller = None


class Controller:
    def __init__(self, panel, status):
        self.panel, self.status_label = panel, status
        override=viewport.register()
        override.gpu_image.frame=None
        override.gpu_image.displayed_id=0
        override.quad.frame=None
        override.has_image=False
        self.engine = Engine()
        self.engine.gpu = bool(self.engine.config.get("gpu_transport", False))
        self.force = True
        self.presented_once = False
        self.scene_stream = None
        self.material_specs = []
        self.timings = {}
        self.quality = InteractionQuality()
        self.changes = SceneChanges()
        self.light_links = LightLinks()
        self.mesh_names = []
        self.last_diagnostics = 0
        self.last_quality = None
        self.in_tick = False
        self.waiting_for_view = False
        self.missing_view_since = None
        self.suspended = False
        self.capture_active = False
        self.capture_key = None
        self.capture_records = []
        self.capture_error = None
        self.capture_syncing = False
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        # Use the later time-change callback; extraction still explicitly evaluates output meshes.
        self.playback_callback = om.MDGMessage.addForceUpdateCallback(self.time_changed)
        self.pre_render_callback = omui.MUiMessage.add3dViewPreRenderMsgCallback(panel, self.before_draw)
        self.engine.start()
        self.timer.start(int(self.engine.config["interval_ms"]))

    def tick(self, *args, refresh=True):
        if self.in_tick or self.capture_syncing or capture.active():
            return
        if not cmds.modelPanel(self.panel, exists=True):
            stop()
            return
        # Maya retains modelPanel nodes after closing a tear-off or rebuilding
        # a layout. Their M3dView may temporarily be unavailable (or 1x1).
        view = panel_view(self.panel)
        if view is None:
            if self.missing_view_since is None:
                self.missing_view_since = time.monotonic()
            self.waiting_for_view = True
            self.engine.status = ("En pausa: renderizador liberado hasta que vuelva el panel" if self.suspended
                                  else "En pausa: esperando la vista del panel de Maya")
            if not self.suspended and time.monotonic() - self.missing_view_since >= 3:
                try:
                    self.suspend_view()
                except Exception:
                    self.engine.status = "No se pudo suspender el renderizador: " + traceback.format_exc()
                    self.timer.setInterval(1000)
                    return
            self.timer.setInterval(100)
            return
        if self.waiting_for_view:
            self.waiting_for_view = False
            self.missing_view_since = None
            if self.suspended:
                try:
                    self.engine.start()
                except Exception:
                    detail = traceback.format_exc()
                    try:
                        self.engine.stop()
                    except Exception:
                        pass
                    self.waiting_for_view = True
                    self.timer.setInterval(1000)
                    self.engine.status = "No se pudo reiniciar Blender: " + detail
                    return
                self.suspended = False
            self.force = True
            self.timer.setInterval(int(self.engine.config["interval_ms"]))
        self.in_tick = True
        try:
            tick_started = time.perf_counter()
            if self.last_quality!=self.engine.config["max_width"]:
                sync_quality_menu(self.engine.config["max_width"])
                self.last_quality=self.engine.config["max_width"]
            if self.presented_once and cmds.modelEditor(self.panel,query=True,rendererOverrideName=True)!=viewport.NAME:
                stop()
                return
            received = self.engine.poll()
            if self.engine.gpu and viewport.register().gpu_image.displayed_id:
                self.presented_once = True
            # While the renderer is busy, avoid thousands of Maya commands per
            # second just to read the same controls. Always poll the IPC first.
            if not received and not self.engine.available:
                return
            state = native_controls.read(self.panel)
            self.engine.playing = self.changes.playing
            override = viewport.register()
            override.native = state
            native_display = state["displayAppearance"] in ("wireframe", "points", "boundingBox")
            if native_display and override.gpu_image.frame:
                # Acknowledgement means released, not merely drawn: the producer
                # must never overwrite a texture which this panel still holds.
                held_id = override.gpu_image.frame["id"]
                override.gpu_image.frame = None
                override.has_image = False
                if self.engine.shared: self.engine.shared.acknowledge(held_id)
            if received:
                if not self.presented_once:
                    # Opening a scene can queue Maya's panel-state restoration
                    # after attach(). Bind when the first real frame is ready.
                    cmds.modelEditor(self.panel,edit=True,rendererName="vp2Renderer",rendererOverrideName=viewport.NAME)
                self.timings["response_age_ms"] = (time.perf_counter() - self.engine.last_response.get("finished_at", time.perf_counter())) * 1000
                if self.engine.frame:
                    if not native_display: override.set_frame(self.engine.frame)
                    if self.engine.gpu:
                        self.engine.shared.acknowledge(self.engine.frame["id"] if native_display else self.engine.frame["id"]-1)
                else:
                    viewport.register().set_image(self.engine.image)
                refresh_started = time.perf_counter()
                if refresh:
                    view.refresh(False, True)
                if self.engine.gpu and not native_display:
                    self.presented_once = self.presented_once or override.gpu_image.displayed_id == self.engine.received_id
                elif not self.engine.gpu:self.presented_once=True
                self.timings["refresh_ms"] = (time.perf_counter() - refresh_started) * 1000
                if not self.engine.shared:
                    self.engine.prune_frames()
            if self.engine.available:
                export_started = time.perf_counter()
                camera = cmds.modelPanel(self.panel, query=True, camera=True)
                aspect = max(1, view.portWidth()) / float(max(1, view.portHeight()))
                width = max(64, min(1920, int(self.engine.config["max_width"])))
                height = max(64, min(1920, int(width / aspect)))
                data = self.snapshot(camera, width, height, state)
                self.quality.apply(data, self.engine.config, self.changes.playing)
                self.timings["export_ms"] = (time.perf_counter() - export_started) * 1000
                submit_started = time.perf_counter()
                submitted = self.engine.submit(data, force=self.force)
                self.timer.setInterval(int(self.engine.config['interval_ms']) if submitted else 16)
                self.timings["submit_ms"] = (time.perf_counter() - submit_started) * 1000
                self.force = False
            self.timings["tick_ms"] = (time.perf_counter() - tick_started) * 1000
            if self.status_label and cmds.control(self.status_label, exists=True):
                cmds.text(self.status_label, edit=True, label=self.engine.status)
            if time.monotonic() - self.last_diagnostics > 1:
                write_json(self.engine.session / "maya_status.json", {
                    "panel": self.panel, "status": self.engine.status,
                    "sent": self.engine.sent_id, "received": self.engine.received_id})
                self.last_diagnostics = time.monotonic()
        except Exception:
            self.timer.stop()
            self.engine.status = "Error en Maya: ver maya_error.txt"
            (self.engine.session / "maya_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            cmds.warning(traceback.format_exc())
            if self.status_label and cmds.control(self.status_label, exists=True):
                cmds.text(self.status_label, edit=True, label=self.engine.status)
        finally:
            self.in_tick = False

    def snapshot(self, camera, width, height, state):
        if self.changes.reconnect:
            self.changes.refresh_callbacks()
        if self.changes.material_dirty and not self.changes.structural:
            self.changes.structural = any(not cmds.objExists(spec['name']) or exporter.material(spec['name']) != spec
                                          for spec in self.material_specs)
            self.changes.material_dirty = False
        if self.changes.structural or not self.engine.shared or not self.scene_stream:
            data = exporter.snapshot(camera, width, height, int(self.engine.config['samples']),
                                     bool(self.engine.config['studio']), binary=bool(self.engine.shared))
            self.material_specs = data['materials']
            self.mesh_names = [mesh['name'] for mesh in data['meshes']]
            if self.engine.shared:
                if self.scene_stream:
                    self.scene_stream.close()
                self.scene_stream = SceneStream(self.mesh_names)
                data['mesh_delta'] = self.scene_stream.update(initial=True)
            self.changes.structural = self.changes.material_dirty = False
        else:
            data = {'protocol': 1, 'camera': exporter.camera(camera, width, height), 'width': width, 'height': height,
                    'samples': int(self.engine.config['samples']), 'effects': exporter.effects()}
            if self.changes.dirty:
                try:
                    data['mesh_delta'] = self.scene_stream.update()
                except RuntimeError:
                    self.changes.structural = True
                    return self.snapshot(camera, width, height, state)
        self.changes.dirty = False
        data['lights'] = exporter.lights()
        links = self.light_links.read(self.mesh_names, [light['name'] for light in data['lights']])
        for light in data['lights']:
            light.update(links[light['name']])
        native_controls.apply(data, state)
        data['maya_frame'] = cmds.currentTime(query=True)
        return data

    def time_changed(self, *args):
        if capture.active():
            self.changes.dirty = True
            return
        self.tick()

    def capture_changed(self, active):
        self.capture_active = active
        self.capture_key = None
        if active:
            self.capture_records = []
            self.capture_error = None
            self.engine.playing = False
        else:
            if self.engine.session:
                write_json(self.engine.session / 'playblast.json',
                           {'valid': self.capture_error is None, 'frames': self.capture_records, 'error': self.capture_error})
            if self.capture_error:
                cmds.warning('Playblast Eevee incompleto. Los fotogramas fallidos se marcan en rojo; no uses ese archivo como captura válida.')
            self.force = True

    def before_draw(self, *args):
        if not capture.active() or self.capture_syncing:
            return
        if not self.capture_active:
            self.capture_changed(True)
        self.capture_syncing = True
        try:
            width, height = render.MRenderer.outputTargetSize()
            self.capture_frame(max(1, width), max(1, height))
        except Exception:
            self.capture_error = traceback.format_exc()
            override = viewport.register()
            override.gpu_image.frame = None
            override.quad.frame = None
            override.has_image = False
            cmds.warning('Falló la sincronización del playblast Eevee: ' + self.capture_error)
        finally:
            self.capture_syncing = False

    def accept_capture_response(self):
        override = viewport.register()
        if self.engine.frame:
            override.set_frame(self.engine.frame)
            if self.engine.gpu:
                self.engine.shared.acknowledge(self.engine.received_id - 1)
        else:
            override.set_image(self.engine.image)

    def capture_frame(self, width, height):
        target = cmds.currentTime(query=True)
        camera = cmds.modelPanel(self.panel, query=True, camera=True)
        key = (target, width, height, camera)
        if self.capture_key == key:
            return
        if self.engine.process is None:
            self.engine.start()
            self.suspended = self.waiting_for_view = False
            self.missing_view_since = None
            self.changes.structural = True
        self.engine.playing = False
        timeout = float(self.engine.config.get('capture_timeout', 120))
        capture.wait_until(self.engine, lambda: self.engine.available, self.accept_capture_response, timeout)
        self.changes.dirty = True
        state = native_controls.read(self.panel)
        data = self.snapshot(camera, width, height, state)
        viewport.register().native = state
        self.engine.submit(data, force=True)
        token = self.engine.sent_id
        capture.wait_until(self.engine, lambda: self.engine.received_id == token, self.accept_capture_response, timeout)
        if self.engine.last_response.get('maya_frame') != target:
            raise RuntimeError('Eevee devolvió una pose distinta al fotograma solicitado.')
        self.capture_key = key
        self.force = False
        deformed = sum(bool(delta['flags'] & 2) for delta in records(data['mesh_delta'])) if data.get('mesh_delta') else 0
        self.capture_records.append({'maya_frame': target, 'id': token, 'width': width, 'height': height,
                                     'deformed_meshes': deformed})

    def close(self):
        self.timer.stop()
        om.MMessage.removeCallback(self.playback_callback)
        try:
            om.MMessage.removeCallback(self.pre_render_callback)
        except RuntimeError:
            pass  # Maya may already have destroyed the callback with its view.
        self.changes.close()
        self.light_links.close()
        if self.scene_stream:
            self.scene_stream.close()
            self.scene_stream = None
        if cmds.modelPanel(self.panel, exists=True):
            cmds.modelEditor(self.panel, edit=True, rendererOverrideName="")
        self.engine.stop()

    def suspend_view(self):
        """A closed tear-off must not keep a complete Blender scene in VRAM."""
        override = viewport.register()
        override.gpu_image.release()
        override.quad.frame = None
        override.has_image = False
        self.engine.stop()
        self.engine.frame = None
        if self.scene_stream:
            self.scene_stream.close()
            self.scene_stream = None
        self.presented_once = False
        self.changes.structural = True
        self.force = True
        self.suspended = True
        self.engine.status = "En pausa: renderizador liberado hasta que vuelva el panel"


def stop(*args):
    global _controller
    if _controller:
        _controller.close()
        _controller = None


def panel_view(panel):
    """A modelPanel can exist while Maya has no drawable view for it yet."""
    try:
        view = omui.M3dView.getM3dViewFromModelPanel(panel)
        return view if view.portWidth() > 1 and view.portHeight() > 1 else None
    except RuntimeError:
        return None


def refresh(*args):
    if _controller:
        _controller.force = True
        _controller.changes.structural = True
        if not _controller.timer.isActive():
            _controller.timer.start(int(_controller.engine.config["interval_ms"]))


def set_quality(value, *args):
    if _controller:
        _controller.engine.config["max_width"] = int(value)
        _controller.force = True
        sync_quality_menu(int(value))


def sync_quality_menu(width):
    """Keep the optional viewer's resolution label in sync with its settings."""
    if not cmds.window(WINDOW,exists=True):return
    for menu in cmds.lsUI(type="optionMenu",long=True) or []:
        if not menu.startswith(WINDOW+"|"):continue
        items=cmds.optionMenu(menu,query=True,itemListLong=True) or []
        labels=[cmds.menuItem(item,query=True,label=True) for item in items]
        if "640" not in labels or "1280" not in labels:continue
        if "1920" not in labels:cmds.menuItem(label="1920",parent=menu)
        if str(width) in labels or width==1920:cmds.optionMenu(menu,edit=True,value=str(width))


def set_studio(value, *args):
    if _controller:
        _controller.engine.config["studio"] = bool(value)
        _controller.changes.structural = True
        _controller.force = True


def scene_settings(*args, select=True):
    node = "eeveeBridgeSettings"
    if not cmds.objExists(node):
        node = cmds.createNode("network", name=node, skipSelect=True)
    for name, kind, value, minimum, maximum in (
            ("volumetrics", "bool", 0, 0, 1), ("density", "double", 0.015, 0, 10),
            ("fogDistance", "double", 100, 1, 1000000),
            ("fogAutoRange", "bool", 1, 0, 1),
            ("anisotropy", "double", 0.3, -0.99, 0.99), ("bloom", "bool", 0, 0, 1),
            ("bloomThreshold", "double", 0.8, 0, 100), ("bloomStrength", "double", 0.5, 0, 10)):
        if not cmds.attributeQuery(name, node=node, exists=True):
            cmds.addAttr(node, longName=name, attributeType=kind, defaultValue=value,
                         minValue=minimum, maxValue=maximum, keyable=True)
    if not cmds.attributeQuery("fogColor", node=node, exists=True):
        cmds.addAttr(node, longName="fogColor", attributeType="float3", usedAsColor=True)
        for component, value in zip("RGB", (0.8, 0.85, 1)):
            cmds.addAttr(node, longName="fogColor" + component, attributeType="float",
                         parent="fogColor", defaultValue=value, keyable=True)
        cmds.setAttr(node + ".fogColor", 0.8, 0.85, 1, type="float3")
    if select:
        cmds.select(node, replace=True)
    return node


def show_settings(*args):
    from .settings_window import show
    return show(_controller)


def show(*args):
    global _controller
    plugin = str(ROOT / "plug-ins" / "eeveeBridge.py")
    loaded = any(name.rsplit("/", 1)[-1] in ("eeveeBridge", "eeveeBridge.py")
                 for name in (cmds.pluginInfo(query=True, listPlugins=True) or []))
    if not loaded:
        cmds.loadPlugin(plugin)
    api = render.MRenderer.drawAPI()
    if api == render.MRenderer.kDirectX11:
        raise RuntimeError("Eevee Bridge requiere OpenGL: cambia Display > Viewport 2.0 a OpenGL y reinicia Maya.")
    stop()
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    viewport.register().has_image = False
    source = cmds.getPanel(withFocus=True)
    camera = (cmds.modelPanel(source, query=True, camera=True)
              if source in (cmds.getPanel(type="modelPanel") or []) else "persp")
    owner = {"controller": None}
    def window_closed(*args):
        # A queued close from an old window must not stop a newly attached panel.
        if owner["controller"] is not None and _controller is owner["controller"]:
            stop()
    window = cmds.window(WINDOW, title="Eevee · Blender Bridge (experimental)",
                         widthHeight=(980, 700), closeCommand=window_closed)
    form = cmds.formLayout()
    bar = cmds.rowLayout(numberOfColumns=7, adjustableColumn=7, height=34)
    cmds.button(label="Actualizar", command=refresh)
    cmds.button(label="Detener", command=stop)
    cmds.button(label="Ajustes", command=show_settings)
    cmds.text(label="Ancho")
    quality = cmds.optionMenu(changeCommand=set_quality)
    for width in (320, 640, 960, 1280, 1920):
        cmds.menuItem(label=str(width))
    cmds.optionMenu(quality, edit=True, value="640")
    cmds.checkBox(label="Luz de estudio", value=bool(settings()["studio"]), changeCommand=set_studio)
    status = cmds.text(label="Iniciando Eevee...", align="left")
    cmds.setParent(form)
    pane = cmds.paneLayout()
    panel = cmds.modelPanel(label="Eevee Bridge", camera=camera, menuBarVisible=True)
    cmds.modelEditor(panel, edit=True, rendererName="vp2Renderer",
                     rendererOverrideName=viewport.NAME, displayAppearance="smoothShaded",
                     displayTextures=True, grid=False)
    cmds.setParent(form)
    cmds.formLayout(form, edit=True,
                    attachForm=[(bar, "top", 0), (bar, "left", 0), (bar, "right", 0),
                                (pane, "left", 0), (pane, "right", 0), (pane, "bottom", 0)],
                    attachControl=[(pane, "top", 0, bar)])
    cmds.showWindow(window)
    _controller = Controller(panel, status)
    owner["controller"] = _controller
    cmds.scriptJob(uiDeleted=[window, window_closed], runOnce=True)
    return _controller


def attach(panel=None, *args):
    """Use a regular Maya modelPanel, with no separate viewer window."""
    global _controller
    panels = cmds.getPanel(type="modelPanel") or []
    panels = [candidate for candidate in panels if panel_view(candidate) is not None]
    if panel not in panels:
        panel = cmds.getPanel(withFocus=True)
    if panel not in panels or (_controller and panel == _controller.panel and cmds.window(WINDOW, exists=True)):
        visible = cmds.getPanel(visiblePanels=True) or []
        panel = next((p for p in visible if p in panels and (not _controller or p != _controller.panel)), None)
    if panel is None:
        return show()
    if render.MRenderer.drawAPI() == render.MRenderer.kDirectX11:
        raise RuntimeError("Eevee Bridge requiere OpenGL. Configuralo en Preferences > Display y reinicia Maya.")
    if render.MRenderer.findRenderOverride(viewport.NAME) is None:
        cmds.loadPlugin(str(ROOT / "plug-ins" / "eeveeBridge.py"))
    stop()
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    for other in panels:
        if other != panel and cmds.modelPanel(other, exists=True):
            if cmds.modelEditor(other, query=True, rendererOverrideName=True) == viewport.NAME:
                cmds.modelEditor(other, edit=True, rendererOverrideName="")
    viewport.register().has_image = False
    cmds.modelEditor(panel, edit=True, rendererName="vp2Renderer", rendererOverrideName=viewport.NAME)
    _controller = Controller(panel, None)
    return _controller


def install_menu():
    if cmds.about(batch=True):
        return
    remove_menu()
    capture.install()
    main = mel.eval("$tmp = $gMainWindow")
    cmds.menu(MENU, label="Eevee", parent=main, tearOff=True)
    cmds.menuItem(label="Activar en viewport actual", command=lambda *args: attach())
    cmds.menuItem(label="Abrir panel independiente", command=show)
    cmds.menuItem(label="Actualizar", command=refresh)
    cmds.menuItem(label="Ajustes del viewport Eevee", command=show_settings)
    cmds.menuItem(label="Nodo de efectos", command=scene_settings)
    cmds.menuItem(label="Detener Blender", command=stop)
    from . import updates_ui
    updates_ui.install_menu(MENU)


def remove_menu():
    capture.uninstall()
    if cmds.menu(MENU, exists=True):
        cmds.deleteUI(MENU)


atexit.register(stop)
