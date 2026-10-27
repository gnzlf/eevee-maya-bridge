"""Owned Maya GUI: native hotkey commands must change real Eevee silhouettes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import maya.cmds as cmds
import maya.mel as mel
import maya.utils
from PySide2 import QtCore, QtGui

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(os.environ['EEVEE_SMOOTH_PROBE']).resolve()
PROFILE = OUTPUT / 'smooth_regression_profile'
if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() != PROFILE:
    raise RuntimeError('A fresh owned Smooth Mesh Preview profile is required')
sys.path.insert(0, str(ROOT / 'scripts'))
from eevee_maya import ui, viewport, __version__

checks = {}
reports = {}
state = {'deadline': time.monotonic() + 180}
timer = None


def capture(label, key, frame=1):
    cmds.select(state['cube'])
    mel.eval('setDisplaySmoothness %d' % key)
    cmds.select(clear=True)
    cmds.playblast(format='image', compression='png', startTime=frame, endTime=frame,
        filename=str(OUTPUT / label), viewer=False, forceOverwrite=True, percent=100,
        widthHeight=(640, 640), showOrnaments=False, offScreen=True, editorPanelName='modelPanel4')
    image_path = next(OUTPUT.glob(label + '.*.png'))
    image = QtGui.QImage(str(image_path))
    checks[label + '_correct_size'] = (image.width(), image.height()) == (640, 640)
    c = state['controller']
    checks[label + '_exact_frame_without_error'] = c.capture_error is None and bool(c.capture_records) and all(
        r['maya_frame'] == frame for r in c.capture_records)
    background = image.pixelColor(10, 10)
    bg = (background.red(), background.green(), background.blue())
    pixels = 0
    for y in range(image.height()):
        for x in range(image.width()):
            p = image.pixelColor(x, y)
            if max(abs(p.red()-bg[0]), abs(p.green()-bg[1]), abs(p.blue()-bg[2])) > 30:
                pixels += 1
    reports[label] = {'foreground_pixels': pixels, 'sha256': hashlib.sha256(image_path.read_bytes()).hexdigest()}
    return pixels


def finish(error=None):
    timer.stop()
    result = {'passed': error is None and all(checks.values()), 'version': __version__,
              'checks': checks, 'reports': reports, 'error': error, 'pid': os.getpid()}
    (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    ui.stop(); ui.remove_menu(); viewport.deregister()
    QtCore.QTimer.singleShot(200, lambda: cmds.quit(force=True))


def tick():
    c = state['controller']
    if time.monotonic() > state['deadline']:
        finish('Timed out: ' + c.engine.status)
        return
    if not c.presented_once or c.force or not c.engine.available:
        return
    timer.stop()
    try:
        nodes = set(cmds.ls(long=True))
        base = capture('base', 1)
        smooth = capture('smooth', 3)
        cage = capture('cage', 2)
        restored = capture('restored', 1)
        checks['key_3_changes_real_rendered_silhouette'] = .35 * base < smooth < .9 * base
        checks['key_2_has_same_smooth_surface'] = abs(cage - smooth) < .02 * base
        checks['key_1_restores_base_silhouette'] = abs(restored - base) < .01 * base
        checks['preview_does_not_modify_source_topology_or_nodes'] = cmds.polyEvaluate(state['cube'], face=True) == 6 and set(cmds.ls(long=True)) == nodes
        cmds.select(clear=True)
        joint = cmds.joint(name='SmoothPreviewJoint')
        cmds.skinCluster(joint, state['cube'], toSelectedBones=True)
        for frame, angle in ((1, 0), (2, 30)):
            cmds.setKeyframe(joint, attribute='rotateZ', time=frame, value=angle)
        capture('skin_pose_1', 3, 1)
        capture('skin_pose_2', 3, 2)
        checks['skinned_smooth_geometry_changes_between_frames'] = reports['skin_pose_1']['sha256'] != reports['skin_pose_2']['sha256']
        checks['gpu_transport_without_error'] = viewport._override.gpu_image.error is None
        finish()
    except Exception:
        finish(traceback.format_exc())


def start():
    global timer
    cmds.file(new=True, force=True)
    cube = cmds.polyCube(name='SmoothPreviewCube', width=2, height=2, depth=2)[0]
    material = cmds.shadingNode('lambert', asShader=True)
    cmds.setAttr(material + '.color', .8, .15, .05, type='double3')
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.connectAttr(material + '.outColor', sg + '.surfaceShader')
    cmds.sets(cube, edit=True, forceElement=sg)
    cmds.setAttr('persp.translate', 0, 0, 8, type='double3')
    cmds.setAttr('persp.rotate', 0, 0, 0, type='double3')
    cmds.setAttr('perspShape.orthographic', True)
    cmds.setAttr('perspShape.orthographicWidth', 4)
    cmds.modelPanel('modelPanel4', edit=True, camera='persp')
    cmds.modelEditor('modelPanel4', edit=True, displayLights='default', grid=False,
                     displayAppearance='smoothShaded', wireframeOnShaded=False)
    cmds.select(clear=True)
    viewport.register()
    ui.install_menu()
    c = ui.attach('modelPanel4')
    c.engine.config.update(max_width=640, adaptive_quality=False)
    state.update(cube=cube, controller=c)
    timer = QtCore.QTimer(); timer.timeout.connect(tick); timer.start(150)


maya.utils.executeDeferred(start)
