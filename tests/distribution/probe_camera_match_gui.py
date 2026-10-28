"""Owned GUI: compare VP2 and Eevee silhouettes with the same untouched camera."""
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

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=Path(os.environ['EEVEE_CAMERA_PROBE']).resolve()
PROFILE=OUTPUT/'camera_regression_profile'
if Path(os.environ.get('MAYA_APP_DIR','')).resolve()!=PROFILE:
    raise RuntimeError('An owned camera profile is required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__
checks={};reports={};state={'deadline':time.monotonic()+240};timer=None


def mask(path):
    image=QtGui.QImage(str(path)).convertToFormat(QtGui.QImage.Format_RGBA8888)
    buffer=image.constBits()
    if hasattr(buffer,'setsize'):buffer.setsize(image.byteCount())
    data=bytes(buffer)
    return {i for i,(r,g,b) in enumerate(zip(data[0::4],data[1::4],data[2::4]))
            if r>80 and r>g*1.5 and r>b*1.5}


def camera_state():
    result={a:cmds.getAttr(state['shape']+'.'+a) for a in state['attributes']}
    result['world_matrix']=cmds.xform(state['camera'],query=True,worldSpace=True,matrix=True)
    return result


def capture(label,panel):
    cmds.playblast(format='image',compression='png',startTime=1,endTime=1,
        filename=str(OUTPUT/label),viewer=False,forceOverwrite=True,percent=100,
        widthHeight=(960,540),offScreen=True,showOrnaments=False,editorPanelName=panel)
    return mask(next(OUTPUT.glob(label+'.*.png')))


def finish(error=None):
    timer.stop()
    (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),
        'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2),encoding='utf-8')
    ui.stop();ui.remove_menu();viewport.deregister()
    QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def run():
    c=state['controller']
    if time.monotonic()>state['deadline']:finish('Startup timeout: '+c.engine.status);return
    if not c.presented_once or c.force or not c.engine.available:return
    timer.stop()
    try:
        defaults=state['defaults']
        cases=[('default',{}),('overscan',{'overscan':1.3}),('wide_lens',{'focalLength':18}),
               ('long_lens',{'focalLength':85}),('vertical_fit',{'filmFit':2}),
               ('offset_and_squeeze',{'horizontalFilmOffset':.15,'verticalFilmOffset':-.05,'lensSqueezeRatio':1.5}),
               ('pan_zoom',{'panZoomEnabled':True,'horizontalPan':.1,'verticalPan':-.05,'zoom':.8}),
               ('film_roll',{'filmRollValue':20}),('gate',{'displayResolution':True,'overscan':1.3,'filmFit':0}),
               ('post_scale',{'postScale':1.2}),('orthographic',{'orthographic':True,'orthographicWidth':8}),
               ('scaled_orthographic',{'orthographic':True,'orthographicWidth':8})]
        for label,values in cases:
            for a,value in defaults.items():cmds.setAttr(state['shape']+'.'+a,value)
            for a,value in values.items():cmds.setAttr(state['shape']+'.'+a,value)
            scale=2 if label=='scaled_orthographic' else 1
            cmds.setAttr(state['camera']+'.scale',scale,scale,scale,type='double3')
            cmds.select(clear=True)
            before=camera_state()
            native=capture(label+'_vp2',state['reference'])
            eevee=capture(label+'_eevee',c.panel)
            union=len(native|eevee);iou=len(native&eevee)/max(1,union)
            checks[label+'_visible_geometry']=min(len(native),len(eevee))>100
            checks[label+'_same_framing']=iou>.985
            checks[label+'_camera_attributes_unchanged']=camera_state()==before
            checks[label+'_native_projection_received']=bool(c.engine.last_response['camera'].get('viewport'))
            checks[label+'_valid_capture']=c.capture_error is None and bool(c.capture_records)
            reports[label]={'iou':iou,'native_pixels':len(native),'eevee_pixels':len(eevee),
                'native_projection':c.engine.last_response['camera'].get('viewport'),
                'focal_length':before['focalLength']}
        before=camera_state()
        cmds.modelEditor(c.panel,edit=True,rendererOverrideName='')
        native=capture('same_panel_switch_vp2',c.panel)
        cmds.modelEditor(c.panel,edit=True,rendererOverrideName=viewport.NAME)
        eevee=capture('same_panel_switch_eevee',c.panel)
        checks['switch_same_panel_keeps_framing']=len(native&eevee)/max(1,len(native|eevee))>.985
        checks['switch_same_panel_keeps_camera_attributes']=camera_state()==before
        checks['switch_same_panel_has_live_eevee_controller']=ui._controller is not None and ui._controller.capture_error is None
        checks['gpu_transport_without_error']=viewport._override.gpu_image.error is None
        finish()
    except Exception:finish(traceback.format_exc())


def start():
    global timer
    cmds.file(new=True,force=True)
    mel.eval('setNamedPanelLayout "Four View"')
    cam,shape=cmds.camera(name='FramingCamera')
    cmds.setAttr(cam+'.translate',0,0,10,type='double3')
    material=cmds.shadingNode('lambert',asShader=True)
    cmds.setAttr(material+'.color',0,0,0,type='double3');cmds.setAttr(material+'.incandescence',1,0,0,type='double3')
    sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True)
    cmds.connectAttr(material+'.outColor',sg+'.surfaceShader')
    for point in ((-1.5,1,0),(1.5,-.5,-1),(.2,-1.5,1)):
        obj=cmds.polyCube(width=.8,height=.8,depth=.8)[0]
        cmds.setAttr(obj+'.translate',*point,type='double3');cmds.sets(obj,edit=True,forceElement=sg)
    for panel in ('modelPanel1','modelPanel4'):
        cmds.modelPanel(panel,edit=True,camera=cam)
        cmds.modelEditor(panel,edit=True,displayLights='all',grid=False,cameras=False,lights=False,
            manipulators=False,selectionHiliteDisplay=False,displayAppearance='smoothShaded',rendererOverrideName='')
    defaults={'focalLength':35,'overscan':1,'filmFit':1,'horizontalFilmOffset':0,'verticalFilmOffset':0,
              'lensSqueezeRatio':1,'panZoomEnabled':False,'horizontalPan':0,'verticalPan':0,'zoom':1,
              'filmRollValue':0,'displayResolution':False,'postScale':1,'orthographic':False,'orthographicWidth':8}
    for a,v in defaults.items():cmds.setAttr(shape+'.'+a,v)
    cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4')
    c.engine.config.update(max_width=960,adaptive_quality=False)
    state.update(camera=cam,shape=shape,reference='modelPanel1',controller=c,defaults=defaults,attributes=list(defaults))
    timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(150)


maya.utils.executeDeferred(start)
