"""Maya Python API 2.0 plug-in entry point."""
import sys
import inspect
import json
import os
import tempfile
import traceback
from pathlib import Path
import maya.api.OpenMaya as om

ROOT = Path(globals().get("__file__", inspect.currentframe().f_code.co_filename)).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
_active = False


def maya_useNewAPI():
    pass


class EeveeViewportCommand(om.MPxCommand):
    def doIt(self, args):
        from eevee_maya import ui
        action = args.asString(0) if len(args) else "enable"
        if action == "enable":
            self.setResult(ui.attach().panel)
        elif action == "disable":
            ui.stop()
        elif action == "effects":
            self.setResult(ui.scene_settings())
        elif action == "settings":
            self.setResult(ui.show_settings())
        elif action == "status":
            self.setResult(ui._controller.engine.status if ui._controller else "Detenido")
        else:
            raise RuntimeError("eeveeViewport: enable, disable, settings, effects o status")


def initializePlugin(obj):
    global _active
    import maya.cmds as cmds
    plugin = None
    registered = False
    viewport = None
    try:
        from eevee_maya import __version__
        from eevee_maya import viewport
        # Validate UI imports inside the error handler, before registering anything.
        if not cmds.about(batch=True):
            from eevee_maya import ui
        plugin = om.MFnPlugin(obj, "Eevee Maya Bridge", __version__, "Any")
        plugin.registerCommand("eeveeViewport", lambda: EeveeViewportCommand())
        registered = True
        _active = True
        if not cmds.about(batch=True):
            # VP2 may not be ready during auto-load. Keep command/menu loading
            # independent from graphics registration and try it on Maya idle.
            cmds.evalDeferred(_install_menu)
        _write_diagnostic({"ok": True, "version": __version__})
    except Exception:
        _active = False
        detail = traceback.format_exc()
        if registered:
            try:
                if viewport is not None:
                    viewport.deregister()
            except Exception:
                pass
            try:
                plugin.deregisterCommand("eeveeViewport")
            except Exception:
                pass
        location = _write_diagnostic({"ok": False, "error": detail})
        om.MGlobal.displayError("Eevee Maya Bridge: " + detail + "\nDiagnóstico: " + str(location))
        raise


def _write_diagnostic(result):
    """Logging must never prevent loading, including read-only module folders."""
    import maya.cmds as cmds
    result = dict(result, plugin=str(ROOT / "plug-ins" / "eeveeBridge.py"), python=sys.version,
                  pid=os.getpid(), batch=bool(cmds.about(batch=True)))
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "EeveeMayaBridge" / "diagnostics"
    for directory in (base, Path(tempfile.gettempdir()) / "EeveeMayaBridge-diagnostics"):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / ('plugin_load.%d.json' % os.getpid())
            target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
            # Batch/installer probes must not replace the last GUI status.
            if not result['batch']:
                (directory / 'plugin_load.json').write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding='utf-8')
            return target
        except OSError:
            continue
    return "No se pudo escribir; consulta el traceback del Script Editor."


def _install_menu():
    if not _active:
        return
    try:
        from eevee_maya import ui
        ui.install_menu()
    except Exception:
        detail = traceback.format_exc()
        location = _write_diagnostic({"ok": False, "stage": "menu", "error": detail})
        om.MGlobal.displayError("Eevee: " + detail + "\nDiagnóstico: " + str(location))
        return
    _register_renderer()


def _register_renderer(attempt=0):
    if not _active:
        return
    from eevee_maya import ui, viewport, __version__
    import maya.api.OpenMayaRender as render
    try:
        viewport.register()
        _write_diagnostic({'ok': True, 'stage': 'renderer', 'version': __version__,
                           'draw_api': int(render.MRenderer.drawAPI()),
                           'opengl_restart_required': render.MRenderer.drawAPI() == render.MRenderer.kDirectX11})
    except RuntimeError:
        detail = traceback.format_exc()
        location = _write_diagnostic({'ok': False, 'stage': 'renderer', 'attempt': attempt + 1, 'error': detail})
        # During auto-load VP2 can exist before its native renderer is ready.
        # Retry registration without recreating menus, selecting Eevee or starting Blender.
        if attempt < 4:
            ui.QtCore.QTimer.singleShot(min(500 * (attempt + 1), 2000), lambda: _register_renderer(attempt + 1))
        else:
            om.MGlobal.displayError('Eevee no pudo registrar Renderer > Eevee. Usa Eevee > Restaurar opción Renderer > Eevee.\nDiagnóstico: ' + str(location))


def uninitializePlugin(obj):
    global _active
    _active = False
    try:
        ui = sys.modules.get("eevee_maya.ui")
        viewport = sys.modules.get("eevee_maya.viewport")
        try:
            if ui is not None:
                ui.stop()
        finally:
            try:
                if ui is not None:
                    ui.remove_menu()
            finally:
                if viewport is not None:
                    viewport.deregister()
    finally:
        # A missing/failed VP2 override must not leave a duplicate command that
        # prevents every subsequent attempt to load this plugin.
        om.MFnPlugin(obj).deregisterCommand("eeveeViewport")
