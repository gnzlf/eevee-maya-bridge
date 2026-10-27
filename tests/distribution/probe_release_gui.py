"""Dedicated release GUI tests. Production path is supplied only through the environment."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import time
import traceback

import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore, QtGui

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(os.environ['EEVEE_RELEASE_PROBE']).resolve()
PROFILE = OUTPUT / 'release_regression_profile'
if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() != PROFILE:
    raise RuntimeError('A fresh owned release profile is required')
sys.path.insert(0, str(ROOT / 'scripts'))
from eevee_maya import ui, viewport, __version__

state = {'phase': 'native_start', 'deadline': time.monotonic() + 420, 'busy': False, 'scopes': []}
checks = {}
reports = {}
timer = None


def dispatch(script, result):
    state['result_path'] = ROOT / 'diagnostics' / result
    state['dispatched_at'] = time.time()
    state['scopes'].append(runpy.run_path(str(ROOT / script)))


def completed():
    path = state['result_path']
    if not path.exists() or path.stat().st_mtime < state['dispatched_at']:
        return None
    report = json.loads(path.read_text(encoding='utf-8'))
    if not report.get('passed'):
        raise RuntimeError('A release regression failed: ' + json.dumps(report.get('error')))
    return report


def load_production(source):
    """Open only the explicitly supplied file in this fixture; never run its script nodes."""
    ui.stop()
    viewport.deregister()
    cmds.loadPlugin('mtoa', quiet=True)
    cmds.file(str(source), open=True, force=True, prompt=False, executeScriptNodes=False)
    for node in cmds.ls(type='script') or []:
        if node.rsplit(':', 1)[-1] != 'sceneConfigurationScriptNode':
            continue
        text = cmds.getAttr(node + '.before') or ''
        values = {flag: float(value) for flag, value in re.findall(r'-(min|max)\s+(-?\d+(?:\.\d+)?)', text)}
        if 'min' in values and 'max' in values:
            cmds.playbackOptions(minTime=values['min'], maxTime=values['max'])
    viewport.register()
    cameras = [camera for camera in cmds.ls(type='camera', long=True)
               if cmds.getAttr(camera + '.renderable') and not cmds.camera(camera, query=True, startupCamera=True)]
    cmds.modelPanel('modelPanel4', edit=True, camera=cameras[0] if cameras else 'persp')
    cmds.modelEditor('modelPanel4', edit=True, displayLights='default', wireframeOnShaded=False,
                     displayAppearance='smoothShaded', displayTextures=True)
    return ui.attach('modelPanel4')


def finish(error=None):
    timer.stop()
    if state.get('source'):
        after = hashlib.sha256(state['source'].read_bytes()).hexdigest()
        checks['production_source_unchanged'] = after == state['source_sha256']
    result = {'version': __version__, 'passed': error is None and all(checks.values()),
              'checks': checks, 'reports': reports, 'error': error, 'pid': os.getpid()}
    (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    ui.stop()
    ui.remove_menu()
    viewport.deregister()
    # This process is owned by the release runner and never opens user-selected files.
    if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() == PROFILE:
        QtCore.QTimer.singleShot(200, lambda: cmds.quit(force=True))


def tick():
    if state['busy']:
        return
    state['busy'] = True
    try:
        if time.monotonic() > state['deadline']:
            raise TimeoutError('Release GUI regression timed out in phase ' + state['phase'])
        phase = state['phase']
        if phase == 'native_start':
            if cmds.file(query=True, sceneName=True):
                raise RuntimeError('Release fixture must start untitled')
            viewport.register()
            ui.install_menu()
            dispatch('tests/distribution/probe_native_playblast.py', 'native_playblast_result.json')
            state['phase'] = 'native_wait'
            return
        if phase == 'native_wait':
            report = completed()
            if report is None:
                return
            reports['native_capture'] = report
            checks['native_png_and_avi_full_hd'] = True
            ui.stop()
            dispatch('tests/distribution/probe_startup_playblast.py', 'startup_playblast_result.json')
            state['phase'] = 'cold_wait'
            return
        if phase == 'cold_wait':
            report = completed()
            if report is None:
                return
            reports['cold_capture'] = report
            checks['cold_start_matches_warm_capture'] = True
            ui.stop()
            source = Path(os.environ['EEVEE_PRODUCTION_SCENE']).resolve()
            state['source'] = source
            state['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            controller = load_production(source)
            if controller is None:
                raise RuntimeError('Production scene did not create the test controller')
            controller.engine.config.update(max_width=960, adaptive_quality=False,
                                            shadow_quality='high', shadow_pool_size='auto')
            controller.force = True
            state['controller'] = controller
            state['production_poses'] = []
            state['next_pose'] = int(cmds.playbackOptions(query=True, minTime=True))
            state['phase'] = 'production'
            return
        controller = state['controller']
        if ui._controller is not controller or controller.startup_error:
            raise RuntimeError('Production controller failed or was replaced')
        if controller.engine.last_response.get('error'):
            raise RuntimeError('Production worker failed')
        if not controller.presented_once or not controller.engine.available or controller.force:
            return
        if phase == 'production':
            response = controller.engine.last_response
            state['production_poses'].append({'pose': response.get('maya_frame'), 'meshes': response['meshes'],
                'width': response['width'], 'height': response['height']})
            if len(state['production_poses']) < 3:
                cmds.currentTime(state['next_pose'])
                state['expected_pose'] = state['next_pose']
                state['next_pose'] += 1
                state['phase'] = 'production_pose_wait'
                return
            checks['production_scene_rendered'] = response['meshes'] > 300
            checks['production_gpu_error_free'] = viewport._override.gpu_image.error is None
            target = cmds.currentTime(query=True)
            path = OUTPUT / 'production-frame'
            cmds.playblast(format='image', compression='png', startTime=target, endTime=target,
                filename=str(path), viewer=False, forceOverwrite=True, percent=100,
                widthHeight=(1920, 1080), showOrnaments=False, offScreen=True,
                editorPanelName=controller.panel)
            images = list(OUTPUT.glob('production-frame.*.png'))
            checks['production_full_hd_capture'] = len(images) == 1 and (
                QtGui.QImage(str(images[0])).width(), QtGui.QImage(str(images[0])).height()) == (1920, 1080)
            checks['production_capture_exact_pose'] = bool(controller.capture_records) and all(
                item['maya_frame'] == target for item in controller.capture_records)
            checks['production_capture_no_error'] = controller.capture_error is None
            reports['production'] = {'poses': state['production_poses'], 'source_saved': False}
            finish()
            return
        if phase == 'production_pose_wait':
            if controller.engine.last_response.get('maya_frame') != state['expected_pose']:
                return
            state['phase'] = 'production'
    except Exception:
        finish(traceback.format_exc())
    finally:
        state['busy'] = False


def start():
    global timer
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(150)


maya.utils.executeDeferred(start)
