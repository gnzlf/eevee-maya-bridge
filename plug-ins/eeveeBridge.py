"""Maya Python API 2.0 plug-in entry point."""
import sys
import inspect
from pathlib import Path
import maya.api.OpenMaya as om

ROOT = Path(globals().get("__file__", inspect.currentframe().f_code.co_filename)).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


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
    import maya.api.OpenMaya as om
    import maya.cmds as cmds
    from eevee_maya import viewport
    import json
    import traceback
    from eevee_maya import __version__
    (ROOT / 'diagnostics').mkdir(parents=True,exist_ok=True)
    try:
        plugin = om.MFnPlugin(obj, "Eevee Maya Bridge", __version__, "Any")
        plugin.registerCommand("eeveeViewport", lambda: EeveeViewportCommand())
        if not cmds.about(batch=True):
            viewport.register()
            from eevee_maya import ui
            cmds.evalDeferred(ui.install_menu)
        (ROOT / "diagnostics" / "plugin_load.json").write_text(json.dumps({"ok": True}))
    except Exception:
        (ROOT / "diagnostics" / "plugin_load.json").write_text(json.dumps({"error": traceback.format_exc()}))
        raise


def uninitializePlugin(obj):
    from eevee_maya import ui, viewport
    ui.stop()
    ui.remove_menu()
    viewport.deregister()
    om.MFnPlugin(obj).deregisterCommand("eeveeViewport")
