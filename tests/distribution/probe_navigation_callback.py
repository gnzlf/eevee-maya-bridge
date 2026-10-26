"""Native VP2 redraws must update Eevee even while its Qt timer is stopped."""
import json,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore
from eevee_maya import ui,viewport
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True);cmds.polyCube()
cmds.setAttr('persp.translate',0,0,16,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
cmds.modelPanel('modelPanel4',edit=True,camera='persp');cmds.modelEditor('modelPanel4',edit=True,displayLights='default')
c=ui.attach('modelPanel4');c.engine.config['max_width']=320
view=omui.M3dView.getM3dViewFromModelPanel(c.panel)
state={'phase':0,'deadline':time.monotonic()+60,'checks':{}}

def finish(error=None):
    timer.stop();c.timer.start(1)
    (root/'diagnostics'/'navigation_callback_result.json').write_text(json.dumps({'passed':not error and all(state['checks'].values()),'checks':state['checks'],'error':error},indent=2))

def tick():
    try:
        if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
        if state['phase']==0:
            if not c.presented_once or c.force or not c.engine.available:return
            c.timer.stop();state['first']=c.engine.sent_id;cmds.setAttr('persp.translateX',3);state['phase']=1
        view.refresh(False,True)
        if c.engine.last_response.get('camera',{}).get('matrix',[0]*16)[12]!=(3 if state['phase']==1 else -3):return
        if viewport.register().gpu_image.displayed_id!=c.engine.received_id:return
        checks=state['checks']
        if state['phase']==1:
            checks['native_redraw_submits_without_qt']=c.engine.sent_id>state['first'] and not c.timer.isActive()
            checks['native_redraw_presents_new_camera']=c.engine.received_id>state['first']
            cmds.setAttr('persp.translateX',-3);state['phase']=2;return
        checks['second_camera_update_without_qt']=not c.timer.isActive()
        checks['no_recursive_tick']=not c.in_tick
        checks['gpu_error_free']=viewport.register().gpu_image.error is None
        finish()
    except Exception:finish(traceback.format_exc())
timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(50)
