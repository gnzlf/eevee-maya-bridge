"""Exercise focus buttons, Undo/Redo and viewport rays in a dedicated Maya GUI."""
import json,time,traceback
from pathlib import Path
from unittest import mock
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore
from eevee_maya import ui,focus,settings_window
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True)
obj=cmds.polyCube(width=20,height=20,depth=40)[0];cmds.setAttr(obj+'.translateZ',-200)
cmds.setAttr('persp.translate',0,0,0,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3');cmds.setAttr('persp.scale',64,64,64,type='double3')
for attr,value in [('focusDistance',250),('depthOfField',False),('nearClipPlane',.1),('farClipPlane',1000)]:cmds.setAttr('perspShape.'+attr,value)
cmds.setAttr('hardwareRenderingGlobals.renderDepthOfField',False)
panel='modelPanel4';cmds.modelPanel(panel,edit=True,camera='persp');cmds.modelEditor(panel,edit=True,depthOfFieldPreview=False,displayLights='default')
c=ui.attach(panel);c.engine.config['max_width']=320
state={'deadline':time.monotonic()+90}
def run():
    if time.monotonic()>state['deadline']:timer.stop();raise TimeoutError(c.engine.status)
    if c.force or not c.presented_once or c.engine.received_id!=c.engine.sent_id:return
    timer.stop();checks={};error=None
    try:
        ui.show_settings();window=settings_window._window;cmds.select(obj,replace=True)
        window.focus_selection();checks['focus_surface_180cm']=abs(cmds.getAttr('perspShape.focusDistance')-180)<.001
        cmds.undo();checks['undo_restores_distance']=abs(cmds.getAttr('perspShape.focusDistance')-250)<.001
        checks['undo_restores_dof']=not cmds.getAttr('perspShape.depthOfField') and not cmds.getAttr('hardwareRenderingGlobals.renderDepthOfField')
        cmds.redo();checks['redo_restores_surface_focus']=abs(cmds.getAttr('perspShape.focusDistance')-180)<.001 and cmds.getAttr('perspShape.depthOfField')
        cmds.setAttr('perspShape.focusDistance',250)
        view=omui.M3dView.getM3dViewFromModelPanel(panel);x,y,_=view.worldToView(om.MPoint(2,2,-180))
        callback={};dragger=cmds.draggerContext;get_panel=cmds.getPanel;previous=cmds.currentCtx()
        def context(*args,**kwargs):
            if kwargs.get('query') and kwargs.get('anchorPoint'):return (x,y,0)
            if 'pressCommand' in kwargs:callback['press']=kwargs['pressCommand']
            return dragger(*args,**kwargs)
        def panels(*args,**kwargs):return panel if kwargs.get('underPointer') else get_panel(*args,**kwargs)
        selected=cmds.ls(selection=True,long=True)
        with mock.patch.object(cmds,'draggerContext',side_effect=context),mock.patch.object(cmds,'getPanel',side_effect=panels):
            window.pick_focus();callback['press']()
        checks['viewport_ray_focus_180cm']=abs(cmds.getAttr('perspShape.focusDistance')-180)<.001
        checks['selection_preserved']=cmds.ls(selection=True,long=True)==selected
        cmds.undo();checks['pick_undo_restores_distance']=abs(cmds.getAttr('perspShape.focusDistance')-250)<.001
        cmds.setToolTo(previous)
    except Exception:error=traceback.format_exc()
    (root/'diagnostics'/'focus_gui_result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'error':error},indent=2))
timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(150)
