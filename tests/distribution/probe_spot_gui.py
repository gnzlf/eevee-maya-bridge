"""Real Maya/EEVEE spot illumination, shadow, scale and parameter captures."""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore,QtGui
ROOT=Path(os.environ.get('EEVEE_INSTALLED_ROOT',Path(__file__).resolve().parents[2]));OUTPUT=Path(os.environ['EEVEE_SPOT_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUTPUT/'spot_regression_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,exporter,__version__
checks={};reports={};state={'deadline':time.monotonic()+180};timer=None


def capture(label):
 c=state['controller'];cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(OUTPUT/label),viewer=False,forceOverwrite=True,percent=100,widthHeight=(960,540),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
 image=QtGui.QImage(str(next(OUTPUT.glob(label+'.*.png'))))
 def rgb(x,y):
  pixels=[image.pixelColor(x+i,y+j) for i in range(-3,4) for j in range(-3,4)]
  return [sum(getattr(p,k)() for p in pixels)/len(pixels) for k in ('red','green','blue')]
 checks[label+'_valid_capture']=not c.capture_error and bool(c.capture_records)
 reports[label]={'center':rgb(480,270),'side':rgb(720,270),'lights':c.engine.last_response['eevee_state']['light_details']}
 return reports[label]['center'][0]


def finish(error=None):
 timer.stop();(OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def tick():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  spot=state['spot'];parent=state['parent']
  cmds.setAttr(spot+'.intensity',0);dark=capture('zero')
  cmds.setAttr(spot+'.intensity',1);lit=capture('default')
  checks['new_default_spot_lights_surface']=lit>dark+25
  cmds.setAttr(spot+'.intensity',.1);dim=capture('dim');checks['intensity_controls_render']=dark+5<dim<lit-15
  cmds.setAttr(parent+'.translateZ',25);cmds.setAttr(spot+'.intensity',1);far=capture('far');checks['normal_spot_is_not_culled_at_25_cm']=far>dark+.5
  cmds.setAttr(parent+'.translateZ',5)
  cmds.setAttr(state['plane']+'.translateZ',-20);moved=capture('receiver_moved');checks['moving_receiver_updates_range']=abs(moved-far)<3
  cmds.setAttr(state['plane']+'.translateZ',0)
  cmds.setAttr(spot+'.intensity',1);cmds.setAttr(spot+'.useRayTraceShadows',True);cmds.modelEditor(c.panel,edit=True,shadows=True)
  shadow=capture('shadows');checks['shadows_do_not_extinguish_light']=shadow>dark+25
  cmds.setAttr(parent+'.scale',15,15,15,type='double3');scaled=capture('scaled')
  checks['native_gizmo_scale_does_not_extinguish_light']=scaled>dark+25
  checks['uniform_scale_preserves_illumination']=abs(scaled-shadow)<3
  cmds.setAttr(parent+'.scale',1,1,1,type='double3');cmds.setAttr(spot+'.dropoff',114);drop=capture('dropoff_114');checks['high_dropoff_keeps_center_lit']=drop>dark+20
  cmds.setAttr(spot+'.dropoff',0);cmds.setAttr(parent+'.rotateY',180);back=capture('back');checks['spot_emits_along_local_negative_z']=back<dark+3
  cmds.setAttr(parent+'.rotateY',0);cmds.setAttr(spot+'.coneAngle',120);wide=capture('wide');checks['cone_angle_widens_footprint']=reports['wide']['side'][0]>reports['default']['side'][0]+20
  cmds.setAttr(spot+'.coneAngle',40);cmds.setAttr(spot+'.penumbraAngle',20);capture('penumbra')
  cmds.modelEditor(c.panel,edit=True,displayLights='active');cmds.select(parent);selected=capture('selected');checks['native_selected_spot_lights_surface']=selected>dark+25
  cmds.select(state['plane']);unselected=capture('unselected');checks['unselected_spot_does_not_enable_headlight']=unselected<dark+3
  cmds.select(parent);cmds.setAttr(spot+'.penumbraAngle',0);cmds.setAttr('perspShape.orthographic',False)
  group=cmds.group(state['plane'],parent,'persp',name='OffsetCameraFixture')
  cmds.setAttr(group+'.translate',-.13,7.97,19.04,type='double3');cmds.setAttr(group+'.rotate',13,19,7,type='double3')
  offset=capture('offset_perspective');checks['rotated_translated_camera_keeps_spot_lit']=offset>dark+25
  checks['eevee_classifies_native_perspective_correctly']=c.engine.last_response['render_camera']['projection_kind']=='perspective'
  checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())


def start():
 global timer
 cmds.file(new=True,force=True);plane=cmds.polyPlane(width=8,height=8,axis=(0,0,1))[0]
 mat=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(mat+'.color',.5,.5,.5,type='double3');sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(plane,edit=True,forceElement=sg)
 spot=cmds.spotLight();parent=cmds.listRelatives(spot,parent=True,fullPath=True)[0];cmds.setAttr(parent+'.translateZ',5)
 cmds.setAttr('persp.translate',0,0,12,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3');cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',10)
 cmds.modelPanel('modelPanel4',edit=True,camera='persp');cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,manipulators=False,selectionHiliteDisplay=False)
 cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
 state.update(controller=c,spot=spot,parent=parent,plane=plane);timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
maya.utils.executeDeferred(start)
