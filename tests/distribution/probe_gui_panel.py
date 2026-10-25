"""Simulate a temporarily missing M3dView on the actual GUI controller."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import maya.cmds as cmds
from eevee_maya import ui
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):
    raise RuntimeError('Dedicated regression Maya required')
c=ui._controller
if c is None or not c.timer.isActive():raise RuntimeError('A running test controller is required')
process=c.engine.process
sent=c.engine.sent_id
with mock.patch.object(ui,'omui',SimpleNamespace(M3dView=SimpleNamespace(
        getM3dViewFromModelPanel=mock.Mock(side_effect=RuntimeError('(kFailure): Object does not exist'))))):
    c.tick()
    paused=c.waiting_for_view and c.timer.isActive() and c.timer.interval()==100 and c.engine.sent_id==sent
c.tick()
checks={'missing_view_pauses_without_error':paused,
        'available_view_resumes':not c.waiting_for_view and c.timer.isActive(),
        'worker_process_preserved':c.engine.process is process,
        'normal_interval_restored':c.timer.interval()==int(c.engine.config['interval_ms'])}
# Wait for the request made on resume, then verify redraw-only work does not
# re-evaluate every mesh. A second pass verifies real dirtiness still does.
import time,traceback
from PySide2 import QtCore
state={'phase':0,'deadline':time.monotonic()+60}
def tick():
    try:
        if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
        if not c.engine.available or c.force:return
        if state['phase']==0:
            c.changes.dirty=False;c.force=True
            with mock.patch.object(c.scene_stream,'update',wraps=c.scene_stream.update) as update:
                c.tick()
            checks['redraw_does_not_rescan_meshes']=update.call_count==0
            state['phase']=1
        elif state['phase']==1:
            c.changes.dirty=True;c.force=True
            with mock.patch.object(c.scene_stream,'update',wraps=c.scene_stream.update) as update:
                c.tick()
            checks['geometry_dirtiness_still_evaluates']=update.call_count==1
            state['phase']=2
        elif state['phase']==2:
            old_process=c.engine.process
            state['settings']=dict(c.engine.config)
            with mock.patch.object(ui,'omui',SimpleNamespace(M3dView=SimpleNamespace(
                    getM3dViewFromModelPanel=mock.Mock(side_effect=RuntimeError('view closed'))))):
                c.missing_view_since=time.monotonic()-4
                c.tick()
            checks['closed_view_releases_worker']=c.suspended and c.engine.process is None and old_process.poll() is not None
            checks['closed_view_releases_scene_cache']=c.scene_stream is None and not ui.viewport.register().has_image
            c.tick()
            checks['returning_view_restarts_worker']=not c.suspended and c.engine.process is not None and c.engine.process is not old_process
            state['phase']=3
        else:
            if ui.viewport.register().gpu_image.displayed_id!=c.engine.received_id:return
            checks['image_recovers_after_worker_restart']=c.engine.received_id>0 and ui.viewport.register().has_image
            checks['restart_preserves_user_settings']=c.engine.config==state['settings']
            timer.stop()
            (root/'diagnostics'/'panel_lifecycle_result.json').write_text(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2))
    except Exception:
        timer.stop()
        (root/'diagnostics'/'panel_lifecycle_result.json').write_text(json.dumps({'passed':False,'checks':checks,'error':traceback.format_exc()},indent=2))
timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(100)
