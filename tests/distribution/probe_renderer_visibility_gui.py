"""Owned GUI regression: Renderer entry on DX11, then real Eevee after GL restart."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

import maya.cmds as cmds
import maya.mel as mel
import maya.utils
import maya.OpenMayaUI as qtui
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as render
import maya.api.OpenMaya as om
from PySide2 import QtCore, QtWidgets, QtGui
from shiboken2 import wrapInstance

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(os.environ['EEVEE_RENDERER_PROBE']).resolve()
PROFILE = OUTPUT / 'renderer_regression_profile'
MODE = os.environ['EEVEE_RENDERER_PROBE_MODE']
if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() != PROFILE:
    raise RuntimeError('A dedicated renderer profile is required')
sys.path.insert(0, str(ROOT / 'scripts'))
from eevee_maya import ui, viewport, settings_window, __version__

spec = importlib.util.spec_from_file_location('eevee_renderer_probe_entry', ROOT / 'plug-ins/eeveeBridge.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
checks = {}
state = {'phase': 0, 'deadline': time.monotonic() + 120}
timer = None


def menu_commands():
    menus = cmds.lsUI(menus=True, long=True) or []
    menu = next(item for item in menus if 'modelPanel4|' in item
                and 'buildRendererMenu' in str(cmds.menu(item, query=True, postMenuCommand=True)))
    mel.eval(cmds.menu(menu, query=True, postMenuCommand=True))
    items = cmds.menu(menu, query=True, itemArray=True)
    eevee = next(item for item in items if cmds.menuItem(item, query=True, label=True) == 'Eevee')
    box = next(item for item in items if item.split('|')[-1] == 'EeveeBridgeOptionBox')
    native = next(item for item in items if item.split('|')[-1] == 'OGSRenderer')
    return {key: cmds.menuItem(item, query=True, command=True)
            for key, item in [('eevee', eevee), ('box', box), ('native', native)]}


def scene_state():
    return (cmds.file(query=True, modified=True), tuple(sorted(cmds.ls(long=True))),
            cmds.currentTime(query=True), cmds.ls(selection=True, long=True))


def finish(error=None):
    timer.stop()
    result = {'version': __version__, 'mode': MODE, 'passed': error is None and all(checks.values()),
              'checks': checks, 'error': error, 'pid': os.getpid()}
    (OUTPUT / (MODE + '-result.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    entry._active = False
    ui.stop(); ui.remove_menu(); viewport.deregister()
    if not cmds.file(query=True, sceneName=True):
        QtCore.QTimer.singleShot(200, lambda: cmds.quit(force=True))


def tick():
    try:
        if time.monotonic() > state['deadline']:
            raise TimeoutError('Renderer visibility test timed out')
        if state['phase'] == 0:
            if cmds.file(query=True, sceneName=True):
                raise RuntimeError('Fixture must start untitled')
            expected = render.MRenderer.kDirectX11 if MODE == 'dx' else render.MRenderer.kOpenGLCoreProfile
            checks['actual_graphics_api'] = render.MRenderer.drawAPI() == expected
            if not checks['actual_graphics_api']:
                raise RuntimeError('Unexpected real graphics API: ' + str(render.MRenderer.drawAPI()))
            if MODE == 'gl':
                cmds.polyCube(name='RendererProbeCube')
                cmds.viewFit('persp', all=True)
            entry._active = True
            # Exercise the actual deferred plugin registration path; no test
            # pre-registration of the override, which previously masked DX skips.
            cmds.evalDeferred(entry._install_menu)
            state['phase'] = 1
            return
        if state['phase'] == 1:
            if render.MRenderer.findRenderOverride(viewport.NAME) is None:
                return
            commands = state['commands'] = menu_commands()
            checks['eevee_in_native_renderer_list'] = viewport.NAME in cmds.modelEditor('modelPanel4', query=True, rendererOverrideList=True)
            checks['native_option_box_exists'] = bool(commands['box'])
            checks['registration_does_not_start_blender'] = ui._controller is None
            state['before'] = scene_state()
            mel.eval(commands['box'])
            checks['options_compatibility_mode_matches_api'] = settings_window._window.compatibility_only == (MODE == 'dx')
            if MODE == 'dx':
                checks['opening_options_does_not_modify_scene'] = state['before'] == scene_state()
                widget = wrapInstance(int(qtui.MQtUtil.findWindow(settings_window.WINDOW)), QtWidgets.QWidget)
                widget.grab().save(str(OUTPUT / 'dx-options.png'))
                buttons = [button for button in widget.findChildren(QtWidgets.QPushButton) if 'Configurar OpenGL' in button.text()]
                prefdir = Path(cmds.internalVar(userPrefDir=True)).resolve()
                if PROFILE not in prefdir.parents:
                    raise RuntimeError('Preference directory is outside the disposable profile')
                buttons[0].click()
                checks['button_saves_opengl_for_restart'] = cmds.optionVar(query='vp2RenderingEngine') == 'OpenGLCoreProfile'
                checks['button_does_not_switch_live_context'] = render.MRenderer.drawAPI() == render.MRenderer.kDirectX11
                checks['button_preserves_scene'] = state['before'] == scene_state()
            cmds.deleteUI(settings_window.WINDOW)
            mel.eval(commands['eevee'])
            state['phase'] = 2
            return
        view = omui.M3dView.getM3dViewFromModelPanel('modelPanel4')
        view.refresh(False, True)
        if MODE == 'dx':
            notice = viewport._override.graphics_notice
            if not notice.draws:
                return
            checks['dx_shows_native_notice'] = notice.draws > 0
            checks['dx_does_not_start_blender'] = ui._controller is None
            checks['dx_does_not_use_gpu_blit'] = viewport._override.gpu_image not in viewport._override.operations
            image = om.MImage(); view.readColorBuffer(image, True)
            image.writeToFile(str(OUTPUT / 'dx-viewport.png'), 'png')
            cmds.playblast(format='image', compression='png', startTime=1, endTime=1,
                filename=str(OUTPUT / 'dx-invalid-capture'), viewer=False, forceOverwrite=True,
                widthHeight=(320, 180), percent=100, offScreen=True,
                showOrnaments=False, editorPanelName='modelPanel4')
            images = list(OUTPUT.glob('dx-invalid-capture.*.png'))
            color = QtGui.QImage(str(images[0])).pixelColor(160, 90) if images else None
            checks['dx_capture_marked_invalid_red'] = bool(color and color.red() > 100 and color.green() < 40)
            mel.eval(state['commands']['native'])
            checks['native_viewport_can_be_restored'] = cmds.modelEditor('modelPanel4', query=True, rendererOverrideName=True) == ''
            finish()
            return
        controller = ui._controller
        if controller and controller.startup_error:
            raise RuntimeError(controller.startup_error)
        if controller is None or not controller.presented_once:
            return
        checks['gl_after_restart_renders_eevee'] = controller.engine.last_response.get('meshes') == 1
        checks['gl_gpu_error_free'] = viewport._override.gpu_image.error is None
        checks['gl_does_not_show_compatibility_notice'] = viewport._override.graphics_notice not in viewport._override.operations
        finish()
    except Exception:
        finish(traceback.format_exc())


def start():
    global timer
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(200)


maya.utils.executeDeferred(start)
