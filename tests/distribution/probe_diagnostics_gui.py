"""Owned Maya GUI fixture: real menu actions, diagnostic windows and GPU frames.

Launch in a fresh profile named diagnostics_regression_profile with
EEVEE_DIAGNOSTICS_PROBE pointing to its parent output directory.
"""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from unittest import mock

import maya.cmds as cmds
import maya.utils
import maya.OpenMayaUI as qtui
import maya.api.OpenMayaUI as omui
import maya.api.OpenMaya as om
from PySide2 import QtCore, QtWidgets
from shiboken2 import wrapInstance

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
OUTPUT = Path(os.environ['EEVEE_DIAGNOSTICS_PROBE']).resolve()
PROFILE = (OUTPUT / 'diagnostics_regression_profile').resolve()
if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() != PROFILE:
    raise RuntimeError('A dedicated diagnostics GUI profile is required')

from eevee_maya import ui, viewport, diagnostics_ui

checks = {}
state = {'phase': 0, 'deadline': time.monotonic() + 150, 'edits': 0}
timer = None


def fixture_state():
    return (cmds.ls(selection=True, long=True), cmds.currentTime(query=True),
            cmds.file(query=True, modified=True), cmds.undoInfo(query=True, undoName=True),
            tuple(sorted(cmds.ls(long=True))))


def action(item):
    pointer = qtui.MQtUtil.findMenuItem(item)
    if not pointer:
        raise RuntimeError('Missing native Maya menu action: ' + item)
    return wrapInstance(int(pointer), QtWidgets.QAction)


def finish(error=None):
    timer.stop()
    result = {'passed': error is None and all(checks.values()), 'checks': checks,
              'error': error, 'pid': os.getpid()}
    (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    ui.stop()
    ui.remove_menu()
    viewport.deregister()
    # Only this fresh-profile process and its own untitled fixture may exit.
    app_dir = Path(cmds.internalVar(userAppDir=True)).resolve()
    if not cmds.file(query=True, sceneName=True) and (app_dir == PROFILE or PROFILE in app_dir.parents):
        QtCore.QTimer.singleShot(200, lambda: cmds.quit(force=True))


def tick():
    try:
        if time.monotonic() > state['deadline']:
            raise TimeoutError('Diagnostics GUI probe timed out')
        if state['phase'] == 0:
            if cmds.file(query=True, sceneName=True):
                raise RuntimeError('The dedicated GUI fixture must start with an untitled scene')
            ui.install_menu()
            items = cmds.menu(ui.MENU, query=True, itemArray=True) or []
            labels = {cmds.menuItem(item, query=True, label=True): item for item in items}
            state['materials_action'] = action(labels['Revisar materiales (solo lectura)…'])
            state['performance_action'] = action(labels['Guardar diagnóstico de rendimiento…'])
            checks['native_diagnostic_menu_actions_exist'] = True
            mat = cmds.shadingNode('standardSurface', asShader=True, name='AuditSurface')
            remap = cmds.shadingNode('remapColor', asUtility=True, name='AuditRemap')
            cmds.connectAttr(remap + '.outColor', mat + '.baseColor')
            state['cube'] = cmds.polyCube(name='AuditMovingCube')[0]
            cmds.select(state['cube'], replace=True)
            cmds.currentTime(7)
            state['before'] = fixture_state()
            state['materials_action'].trigger()
            state['phase'] = 1
            return
        if state['phase'] == 1:
            pointer = qtui.MQtUtil.findWindow(diagnostics_ui.WINDOW)
            widget = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
            checks['material_window_visible'] = bool(widget and widget.isVisible())
            fields = [item for item in cmds.lsUI(type='scrollField', long=True) or []
                      if item.startswith(diagnostics_ui.WINDOW + '|')]
            text = cmds.scrollField(fields[0], query=True, text=True)
            checks['material_and_issue_visible'] = 'AuditSurface' in text and 'baseColor' in text
            widget.grab().save(str(OUTPUT / 'material-window.png'))
            buttons = [button for button in widget.findChildren(QtWidgets.QPushButton)
                       if 'Guardar informe' in button.text()]
            path = OUTPUT / 'materials.json'
            with mock.patch.object(cmds, 'fileDialog2', return_value=[str(path)]):
                buttons[0].click()
            exported = path.read_text(encoding='utf-8')
            checks['button_saves_anonymized_report'] = 'AuditSurface' not in exported and 'AuditRemap' not in exported
            before = path.read_bytes()
            with mock.patch.object(cmds, 'fileDialog2', return_value=None):
                buttons[0].click()
            checks['cancel_preserves_existing_report'] = path.read_bytes() == before
            checks['audit_keeps_scene_selection_time_and_undo'] = fixture_state() == state['before']
            checks['audit_does_not_start_engine'] = ui._controller is None
            with mock.patch.object(cmds, 'fileDialog2') as dialog:
                state['performance_action'].trigger()
                checks['inactive_performance_does_not_start_engine'] = ui._controller is None and not dialog.called
            cmds.deleteUI(diagnostics_ui.WINDOW)
            viewport.register()
            cmds.setAttr('persp.translate', 0, 0, 12, type='double3')
            cmds.setAttr('persp.rotate', 0, 0, 0, type='double3')
            cmds.modelEditor('modelPanel4', edit=True, displayAppearance='smoothShaded', grid=False)
            ui.attach('modelPanel4')
            state['phase'] = 2
            return
        controller = ui._controller
        if controller is None:
            raise RuntimeError('Fixture renderer unexpectedly stopped')
        if controller.startup_error or controller.engine.last_response.get('error'):
            raise RuntimeError(controller.startup_error or controller.engine.last_response['error'])
        if not controller.presented_once:
            return
        if state['edits'] < 16:
            state['edits'] += 1
            cmds.setAttr(state['cube'] + '.translateX', (state['edits'] % 4) * .2)
            return
        if controller.engine.sent_id != controller.engine.received_id or controller.force:
            return
        report_path = OUTPUT / 'performance.json'
        before = fixture_state()
        with mock.patch.object(cmds, 'fileDialog2', return_value=[str(report_path)]):
            state['performance_action'].trigger()
        report = json.loads(report_path.read_text(encoding='utf-8'))
        checks['performance_menu_saves_real_gpu_frames'] = report['presented_unique_frames'] >= 3
        checks['performance_records_resolution_and_latency'] = bool(report['actual_resolutions']) and report['submit_to_draw_ms']['count'] >= 3
        checks['performance_keeps_scene_selection_time_and_undo'] = before == fixture_state()
        checks['gpu_error_free'] = viewport._override.gpu_image.error is None
        image = om.MImage()
        omui.M3dView.getM3dViewFromModelPanel('modelPanel4').readColorBuffer(image, True)
        image.writeToFile(str(OUTPUT / 'viewport.png'), 'png')
        finish()
    except Exception:
        finish(traceback.format_exc())


def start():
    global timer
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(200)


maya.utils.executeDeferred(start)
