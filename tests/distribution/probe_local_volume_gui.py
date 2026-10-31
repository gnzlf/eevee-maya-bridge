"""Real Maya/GPU checks for point/sun surfaces and point/area/spot atmosphere.

Only a dedicated, owned profile is accepted. Images and reports stay private.
"""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore,QtGui

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ['EEVEE_LOCAL_VOLUME_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'local_volume_regression_profile':
 raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__
checks={};reports={};state={'deadline':time.monotonic()+420};timer=None

def capture(label,points=None):
 c=state['c']
 (OUT/'progress.json').write_text(json.dumps({'label':label,'time':time.time()}))
 cmds.playblast(format='image',compression='png',startTime=1,endTime=1,
  filename=str(OUT/label),viewer=False,forceOverwrite=True,percent=100,
  widthHeight=(960,540),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
 image=QtGui.QImage(str(next(OUT.glob(label+'.*.png'))))
 checks[label+'_capture']=not c.capture_error and bool(c.capture_records) and (image.width(),image.height())==(960,540)
 def rgb(x,y):
  colors=[image.pixelColor(x+i,y+j) for i in range(-4,5) for j in range(-4,5)]
  return [sum(getattr(p,ch)() for p in colors)/len(colors) for ch in ('red','green','blue')]
 values={name:rgb(*xy) for name,xy in (points or {'center':(480,270)}).items()}
 reports[label]={'pixels':values,'lights':c.engine.last_response['eevee_state']['light_details']}
 return values

def shape(kind):
 parent=cmds.shadingNode(kind,asLight=True)
 return parent,cmds.listRelatives(parent,shapes=True,fullPath=True)[0]

def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'version':__version__,'passed':not error and all(checks.values()),
  'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister()
 QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))

def surface_tests():
 c=state['c'];plane=state['plane']
 for kind in ('pointLight','directionalLight'):
  parent,light=shape(kind);cmds.setAttr(parent+'.translateZ',5)
  cmds.setAttr(light+'.intensity',0);dark=capture(kind+'_zero')['center']
  cmds.setAttr(light+'.intensity',1);lit=capture(kind+'_one')['center']
  checks[kind+'_illuminates']=max(lit)>max(dark)+25
  cmds.setAttr(light+'.intensity',.15);dim=capture(kind+'_dim')['center']
  checks[kind+'_intensity']=max(dark)+3<max(dim)<max(lit)-12
  cmds.setAttr(light+'.intensity',1);cmds.setAttr(light+'.color',.01,.02,1,type='double3')
  blue=capture(kind+'_blue')['center'];checks[kind+'_color']=blue[2]>blue[0]+25
  cmds.select(parent);cmds.modelEditor(c.panel,edit=True,displayLights='active')
  selected=capture(kind+'_selected')['center']
  cmds.select(plane);none=capture(kind+'_unselected')['center']
  checks[kind+'_selection']=max(abs(a-b) for a,b in zip(selected,blue))<3 and max(none)<max(dark)+3
  cmds.modelEditor(c.panel,edit=True,displayLights='all');cmds.select(clear=True)
  cmds.lightlink(light=light,object=plane,b=True)
  unlinked=capture(kind+'_unlinked')['center'];checks[kind+'_light_link']=max(unlinked)<max(dark)+3
  cmds.lightlink(light=light,object=plane,make=True)
  if kind=='directionalLight':
   cmds.setAttr(parent+'.rotateY',180);back=capture(kind+'_back')['center']
   checks['directional_orientation']=max(back)<max(dark)+3
   # Rotate the receiver and sun together to exercise illumination from above.
   cmds.setAttr(parent+'.rotate',-90,0,0,type='double3');cmds.setAttr(plane+'.rotateX',-90)
   cmds.setAttr('persp.translate',0,15,0,type='double3');cmds.setAttr('persp.rotate',-90,0,0,type='double3')
   top=capture(kind+'_top')['center'];checks['directional_from_above']=top[2]>top[0]+25 and max(top)>max(dark)+25
   cmds.setAttr(plane+'.rotateX',0);cmds.setAttr('persp.translate',0,0,15,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  else:
   cmds.setAttr(parent+'.rotate',110,67,21,type='double3');rotated=capture(kind+'_rotated')['center']
   checks['point_rotation_invariant']=max(abs(a-b) for a,b in zip(rotated,blue))<3
  cmds.delete(parent)

def volume_tests():
 from eevee_maya.settings_window import SettingsWindow
 c=state['c'];cmds.delete(state['plane'])
 cmds.setAttr('persp.translate',15,0,-5,type='double3');cmds.setAttr('persp.rotate',0,90,0,type='double3')
 cmds.setAttr('perspShape.orthographicWidth',24)
 cmds.setAttr('perspShape.nearClipPlane',.1);cmds.setAttr('perspShape.farClipPlane',100)
 settings=ui.scene_settings(select=False)
 for key,value in (('density',.035),('fogDistance',30),('fogAutoRange',False),('anisotropy',0)):
  cmds.setAttr(settings+'.'+key,value)
 cmds.setAttr(settings+'.fogColor',1,1,1,type='double3')
 points={'front':(480,270),'back':(160,270),'side':(480,150),'edge':(480,210)}
 for kind in ('pointLight','areaLight','spotLight'):
  parent,light=shape(kind);cmds.setAttr(light+'.intensity',2)
  if kind=='areaLight':cmds.setAttr(parent+'.scale',2,1,1,type='double3')
  if kind=='spotLight':cmds.setAttr(light+'.coneAngle',35)
  cmds.select(parent)
  window=SettingsWindow(c);window.prepare_volume()
  checks[kind+'_volume_button']=cmds.getAttr(settings+'.volumetrics') and cmds.getAttr(light+'.eeveeVolume')
  window.timer.stop();cmds.deleteUI(window.window);cmds.select(clear=True)
  cmds.setAttr(light+'.eeveeVolumeFactor',0);off=capture(kind+'_volume_off',points)
  cmds.setAttr(light+'.eeveeVolumeFactor',1);on=capture(kind+'_volume_on',points)
  delta={name:max(on[name])-max(off[name]) for name in points}
  checks[kind+'_volume_visible']=delta['front']>5
  reports[kind+'_volume_delta']=delta
  cmds.setAttr(light+'.eeveeVolumeFactor',.2);dim=capture(kind+'_volume_dim',points)
  checks[kind+'_volume_factor']=max(off['front'])+1<max(dim['front'])<max(on['front'])-3
  cmds.setAttr(light+'.eeveeVolumeFactor',1);cmds.setAttr(light+'.eeveeVolume',False)
  disabled=capture(kind+'_volume_disabled',points)
  checks[kind+'_volume_switch']=max(abs(a-b) for a,b in zip(off['front'],disabled['front']))<3
  cmds.setAttr(light+'.eeveeVolume',True);cmds.setAttr(light+'.emitDiffuse',False);cmds.setAttr(light+'.emitSpecular',False)
  independent=capture(kind+'_volume_only',points)
  checks[kind+'_volume_independent_of_surface']=max(abs(a-b) for a,b in zip(on['front'],independent['front']))<3
  cmds.setAttr(light+'.color',.01,.02,1,type='double3');blue=capture(kind+'_volume_blue',points)
  checks[kind+'_volume_color']=blue['front'][2]>blue['front'][0]+5
  cmds.modelEditor(c.panel,edit=True,displayLights='active');cmds.select(clear=True)
  none=capture(kind+'_volume_unselected',points)
  checks[kind+'_volume_selection_off']=max(none['front'])<max(off['front'])+3
  cmds.select(parent);selected=capture(kind+'_volume_selected',points)
  checks[kind+'_volume_selection_on']=selected['front'][2]>none['front'][2]+5
  cmds.modelEditor(c.panel,edit=True,displayLights='all');cmds.select(clear=True)
  if kind=='pointLight':checks['point_volume_is_omnidirectional']=delta['back']>5 and delta['side']>3
  else:
   checks[kind+'_volume_front_only']=delta['back']<max(4,delta['front']*.15)
   cmds.setAttr(light+'.color',1,1,1,type='double3');cmds.setAttr(parent+'.rotateY',180)
   flipped=capture(kind+'_volume_reversed',points)
   checks[kind+'_volume_follows_orientation']=max(flipped['back'])>max(off['back'])+5 and max(flipped['front'])<max(on['front'])-5
   if kind=='spotLight':checks['spot_volume_remains_conical']=delta['side']<max(4,delta['front']*.15)
  cmds.delete(parent)
 checks['gpu_error_free']=viewport._override.gpu_image.error is None

def shadow_tests():
 c=state['c'];plane=state['plane']
 blocker=cmds.polyCube(width=1.4,height=1.4,depth=.4)[0]
 cmds.setAttr(blocker+'.translate',-1.2,0,2,type='double3')
 points={'receiver':(480,270)}
 for kind in ('pointLight','areaLight','directionalLight','spotLight'):
  parent,light=shape(kind)
  cmds.setAttr(parent+'.translate',-3,0,5,type='double3');cmds.setAttr(parent+'.rotateY',-30.9637565)
  if kind=='areaLight':cmds.setAttr(parent+'.scale',.25,.25,1,type='double3')
  cmds.setAttr(light+'.useRayTraceShadows',True)
  cmds.modelEditor(c.panel,edit=True,shadows=False);cmds.select(clear=True)
  off=capture(kind+'_shadow_off',points)['receiver']
  cmds.modelEditor(c.panel,edit=True,shadows=True)
  on=capture(kind+'_shadow_on',points)['receiver']
  checks[kind+'_native_shadow_switch']=max(off)>30 and max(on)<max(off)*.55
  cmds.lightlink(light=light,object=blocker,b=True,shadow=True)
  unlinked=capture(kind+'_shadow_unlinked',points)['receiver']
  checks[kind+'_shadow_link']=max(unlinked)>max(on)+20
  cmds.delete(parent)
 cmds.delete(blocker,plane)
 cmds.setAttr('persp.translate',15,0,-5,type='double3');cmds.setAttr('persp.rotate',0,90,0,type='double3')
 cmds.setAttr('perspShape.orthographicWidth',24);cmds.setAttr('perspShape.farClipPlane',100)
 settings=ui.scene_settings(select=False)
 for key,value in (('volumetrics',True),('density',.035),('fogDistance',30),('fogAutoRange',False),('anisotropy',0)):
  cmds.setAttr(settings+'.'+key,value)
 cmds.setAttr(settings+'.fogColor',1,1,1,type='double3')
 blocker=cmds.polyCube(width=20,height=20,depth=.15)[0];cmds.setAttr(blocker+'.translateZ',-3)
 for kind in ('pointLight','areaLight','spotLight'):
  parent,light=shape(kind);cmds.setAttr(light+'.intensity',2);cmds.setAttr(light+'.useRayTraceShadows',True)
  cmds.modelEditor(c.panel,edit=True,shadows=False);cmds.select(clear=True)
  off=capture(kind+'_volume_shadow_off',{'behind_card':(560,270)})['behind_card']
  cmds.modelEditor(c.panel,edit=True,shadows=True)
  on=capture(kind+'_volume_shadow_on',{'behind_card':(560,270)})['behind_card']
  cmds.setAttr(light+'.intensity',0)
  base=capture(kind+'_volume_shadow_dark',{'behind_card':(560,270)})['behind_card']
  # Atmosphere over Maya's background has a nonzero floor. Compare light
  # contribution against that control, rather than expecting black pixels.
  signal=max(off)-max(base);residual=max(on)-max(base)
  checks[kind+'_volume_shadow_occlusion']=signal>3 and residual<max(2,signal*.2)
  cmds.delete(parent)
 checks['gpu_error_free']=viewport._override.gpu_image.error is None

def tick():
 try:
  c=state['c']
  if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
  if not c.presented_once or c.force or not c.engine.available:return
  timer.stop()
  if os.environ.get('EEVEE_LOCAL_VOLUME_PHASE')=='shadows':shadow_tests()
  else:surface_tests();volume_tests()
  finish()
 except Exception:finish(traceback.format_exc())

def start():
 global timer
 try:
  cmds.file(new=True,force=True)
  plane=cmds.polyPlane(width=10,height=10,axis=(0,0,1))[0]
  material=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(material+'.color',.5,.5,.5,type='double3')
  sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(material+'.outColor',sg+'.surfaceShader');cmds.sets(plane,edit=True,forceElement=sg)
  cmds.setAttr('persp.translate',0,0,15,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',12)
  cmds.modelPanel('modelPanel4',edit=True,camera='persp')
  cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,manipulators=False,selectionHiliteDisplay=False)
  for key in ('bloomEnable','ssaoEnable'):cmds.setAttr('hardwareRenderingGlobals.'+key,False)
  cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',True);cmds.setAttr('hardwareRenderingGlobals.multiSampleCount',8)
  cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=960,adaptive_quality=False)
  state.update(c=c,plane=plane);timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
