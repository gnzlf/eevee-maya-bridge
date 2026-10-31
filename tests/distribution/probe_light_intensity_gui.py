"""Compare identical native lights in VP2/Eevee without editing their values.

Run only inside an owned Maya GUI profile. Raw and OCIO display measurements
are separate so display curves cannot be mistaken for intensity conversion.
"""
import ctypes,json,math,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore,QtGui

ROOT=Path(os.environ.get('EEVEE_INSTALLED_ROOT',Path(__file__).resolve().parents[2]))
OUT=Path(os.environ['EEVEE_INTENSITY_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'intensity_regression_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__
state={'deadline':time.monotonic()+600};reports=[];checks={};timer=None

def capture(name):
 c=state['c']
 cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(OUT/name),
  viewer=False,forceOverwrite=True,percent=100,widthHeight=(640,360),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
 image=QtGui.QImage(str(next(OUT.glob(name+'.*.png'))))
 colors=[image.pixelColor(320+i,180+j) for i in range(-4,5) for j in range(-4,5)]
 encoded=[sum(getattr(p,ch)() for p in colors)/len(colors)/255 for ch in ('red','green','blue')]
 view=omui.M3dView.getM3dViewFromModelPanel(c.panel);view.refresh(False,True)
 display=om.MImage();view.readColorBuffer(display,True);w,h=display.getSize();raw=ctypes.string_at(display.pixels(),w*h*4)
 x,y,_=view.worldToView(om.MPoint(0,0,0))
 values=[[raw[4*((y+j)*w+x+i)+ch]/255 for ch in range(3)] for i in range(-4,5) for j in range(-4,5)]
 display.writeToFile(str(OUT/(name+'_display.png')),'png')
 state.setdefault('encoded',{})[name]=encoded
 return [sum(p[ch] for p in values)/len(values) for ch in range(3)]

def pair(label):
 from eevee_maya import exporter
 before=exporter.lights()
 c=state['c'];eevee=capture(label+'_eevee');details=c.engine.last_response['eevee_state']['light_details']
 ticking=c.timer.isActive();c.timer.stop();old=c.in_tick;c.in_tick=True
 try:
  cmds.modelEditor(c.panel,edit=True,rendererOverrideName='')
  native=capture(label+'_vp2')
 finally:
  cmds.modelEditor(c.panel,edit=True,rendererOverrideName=viewport.NAME);c.in_tick=old
  if ticking:c.timer.start(1)
 checks[label+'_maya_values_preserved']=exporter.lights()==before
 return {'eevee':eevee,'vp2':native,'details':details,'capture_eevee':state['encoded'][label+'_eevee'],'capture_vp2':state['encoded'][label+'_vp2']}

def finish(error=None):
 if timer:timer.stop()
 if os.environ.get('EEVEE_INTENSITY_ASSERT')=='1':
  for index,row in enumerate(reports):
   row['max_display_byte_error']=max(abs(a-b)*255 for a,b in zip(row['eevee'],row['vp2']))
   row['max_capture_byte_error']=max(abs(a-b)*255 for a,b in zip(row['capture_eevee'],row['capture_vp2']))
   checks['display_matches_vp2_'+str(index)]=row['max_display_byte_error']<=3
   checks['capture_matches_vp2_'+str(index)]=row['max_capture_byte_error']<=3
 (OUT/'result.json').write_text(json.dumps({'version':__version__,'passed':not error and all(checks.values()),
  'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))

def run():
 c=state['c']
 try:
  if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
  if not c.presented_once or c.force or not c.engine.available:return
  timer.stop()
  if os.environ.get('EEVEE_INTENSITY_MATERIALS')=='1':
   cmds.colorManagementPrefs(edit=True,cmEnabled=False);cmds.modelEditor(c.panel,edit=True,cmEnabled=False)
   cmds.loadPlugin('mtoa',quiet=True)
   for material_kind in ('lambert','standardSurface','aiStandardSurface'):
    mat=cmds.shadingNode(material_kind,asShader=True)
    standard=material_kind!='lambert'
    cmds.setAttr(mat+('.baseColor' if standard else '.color'),.25,.25,.25,type='double3')
    cmds.setAttr(mat+('.base' if standard else '.diffuse'),1)
    if standard:cmds.setAttr(mat+'.specular',0)
    sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(state['plane'],edit=True,forceElement=sg)
    for kind in ('directionalLight','pointLight','spotLight','areaLight','ambientLight'):
     parent=cmds.shadingNode(kind,asLight=True);light=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
     cmds.setAttr(parent+'.translateZ',5);cmds.setAttr(light+'.intensity',16 if kind=='areaLight' else .5)
     if kind=='ambientLight':cmds.setAttr(light+'.ambientShade',1)
     data=pair(material_kind+'_'+kind);data.update(kind=kind,material=material_kind,cm=False)
     reports.append(data);cmds.delete(parent)
   checks['measurements_complete']=len(reports)==15;finish();return
  if os.environ.get('EEVEE_INTENSITY_EXTENDED')=='1':
   cmds.colorManagementPrefs(edit=True,cmEnabled=False);cmds.modelEditor(c.panel,edit=True,cmEnabled=False)
   cmds.loadPlugin('mtoa',quiet=True)
   for kind in ('areaLight','aiAreaLight'):
    parent=cmds.shadingNode(kind,asLight=True);light=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
    cmds.setAttr(light+'.intensity',16)
    for index,(distance,decay,scale,normalize,legacy) in enumerate(((5,0,1,True,False),(10,0,1,True,False),(5,1,1,True,False),(5,2,1,True,False),(5,0,2,True,False),(5,0,2,False,False),(5,0,1,True,True))):
     intensity=.5 if not normalize or legacy else 16
     cmds.setAttr(light+'.intensity',intensity)
     cmds.setAttr(parent+'.translateZ',distance);cmds.setAttr(parent+'.scale',scale,scale,1,type='double3')
     for key,value in (('decayRate',decay),('normalize',normalize),('legacyIntensity',legacy)):
      if cmds.objExists(light+'.'+key):cmds.setAttr(light+'.'+key,value)
     data=pair(kind+'_extended_'+str(index));data.update(kind=kind,intensity=intensity,cm=False,distance=distance,decay=decay,scale=scale,normalize=normalize,legacy=legacy)
     from eevee_maya import exporter
     data['source_spec']=next(s for s in exporter.lights() if s['name']==light)
     reports.append(data)
    cmds.delete(parent)
   checks['measurements_complete']=len(reports)==14;finish();return
  for kind in ('directionalLight','pointLight','spotLight','areaLight','ambientLight'):
   parent=cmds.shadingNode(kind,asLight=True);light=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
   cmds.setAttr(parent+'.translateZ',5)
   if kind=='ambientLight':cmds.setAttr(light+'.ambientShade',0)
   for cm in (False,True):
    cmds.colorManagementPrefs(edit=True,cmEnabled=cm)
    cmds.modelEditor(c.panel,edit=True,cmEnabled=cm)
    for intensity in (.25,1):
     cmds.setAttr(light+'.intensity',intensity);label=kind+'_'+str(cm)+'_'+str(intensity)
     data=pair(label);data.update(kind=kind,intensity=intensity,cm=cm,distance=5,decay=0)
     reports.append(data)
   if kind in ('pointLight','spotLight','areaLight'):
    cmds.colorManagementPrefs(edit=True,cmEnabled=False)
    cmds.modelEditor(c.panel,edit=True,cmEnabled=False)
    for decay,distance in ((0,10),(1,5),(1,10),(2,5),(2,10)):
     cmds.setAttr(light+'.intensity',1);cmds.setAttr(light+'.decayRate',decay);cmds.setAttr(parent+'.translateZ',distance)
     data=pair(kind+'_d'+str(decay)+'_z'+str(distance));data.update(kind=kind,intensity=1,cm=False,distance=distance,decay=decay)
     reports.append(data)
   cmds.delete(parent)
  checks['measurements_complete']=len(reports)==35
  from eevee_maya.settings_window import SettingsWindow
  from eevee_maya import exporter
  cmds.colorManagementPrefs(edit=True,cmEnabled=False);cmds.modelEditor(c.panel,edit=True,cmEnabled=False)
  parent=cmds.shadingNode('pointLight',asLight=True);light=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
  cmds.setAttr(parent+'.translateZ',5);before=exporter.lights()
  window=SettingsWindow(c)
  checks['viewport2_mode_is_default']=cmds.optionMenu(window.intensity_mode,query=True,value=True)=='Aproximar Viewport 2.0'
  window.set_intensity_mode('Conversión anterior de Eevee');previous=capture('mode_legacy')
  checks['legacy_preference_persists']=cmds.optionVar(query='eeveeLightIntensityMode')=='legacy'
  window.set_intensity_mode('Aproximar Viewport 2.0');current=capture('mode_viewport2')
  checks['mode_changes_presentation_without_changing_maya_values']=exporter.lights()==before and current[0]>previous[0]*2 and abs(current[0]-.25)<.012
  checks['viewport2_preference_persists']=cmds.optionVar(query='eeveeLightIntensityMode')=='viewport2'
  window.timer.stop();cmds.deleteUI(window.window);cmds.delete(parent)
  checks['gpu_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())

def start():
 global timer
 try:
  cmds.file(new=True,force=True)
  plane=cmds.polyPlane(width=4,height=4,axis=(0,0,1))[0]
  mat=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(mat+'.color',.25,.25,.25,type='double3');cmds.setAttr(mat+'.diffuse',1)
  sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(plane,edit=True,forceElement=sg)
  cmds.setAttr('persp.translate',0,0,15,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',6)
  cmds.modelPanel('modelPanel4',edit=True,camera='persp')
  cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',
   displayTextures=True,lights=False,manipulators=False,selectionHiliteDisplay=False,exposure=0,gamma=1)
  for key in ('bloomEnable','ssaoEnable'):cmds.setAttr('hardwareRenderingGlobals.'+key,False)
  cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
  state.update(c=c,plane=plane);timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(150)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
