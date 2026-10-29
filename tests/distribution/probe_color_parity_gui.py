"""Compare emissive patches through native Maya and Eevee OCIO GPU displays."""
import ctypes,json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
from PySide2 import QtCore,QtGui,QtWidgets
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_LOOK_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'looks_regression_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,settings_window,exporter
checks={};reports={};state={'deadline':time.monotonic()+180,'files':{}};timer=None
def snap(name):
 cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(OUT/name),viewer=False,forceOverwrite=True,percent=100,widthHeight=(960,540),showOrnaments=False,offScreen=True,editorPanelName='modelPanel4')
 encoded=QtGui.QImage(str(next(OUT.glob(name+'.*.png'))))
 state['files'][name]=[list(encoded.pixelColor(x,270).getRgb()[:3]) for x in (192,480,768)]
 view=omui.M3dView.getM3dViewFromModelPanel('modelPanel4');view.refresh(False,True)
 im=om.MImage();view.readColorBuffer(im,True);w,h=im.getSize();pixels=ctypes.string_at(im.pixels(),w*h*4)
 im.writeToFile(str(OUT/(name+'_display.png')),'png')
 values=[]
 for x in (-3,0,3):
  ix,iy,_=view.worldToView(om.MPoint(x,0,0));i=4*(iy*w+ix);values.append(list(pixels[i:i+3]))
 return values
def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))
def run():
 c=state['c']
 if time.monotonic()>state['deadline']:finish('Timeout '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  for name in ('base','exposure','gamma','raw','view'):
   if name=='exposure':cmds.modelEditor(c.panel,edit=True,exposure=-1)
   if name=='gamma':cmds.modelEditor(c.panel,edit=True,exposure=0,gamma=1.4)
   if name=='raw':cmds.modelEditor(c.panel,edit=True,exposure=0,gamma=1,cmEnabled=False)
   if name=='view':cmds.modelEditor(c.panel,edit=True,cmEnabled=True,viewTransformName='Un-tone-mapped (sRGB)')
   eevee=snap('eevee_'+name)
   cmds.modelEditor(c.panel,edit=True,rendererOverrideName='');native=snap('native_'+name)
   cmds.modelEditor(c.panel,edit=True,rendererOverrideName=viewport.NAME)
   error=max(abs(a-b) for p,q in zip(eevee,native) for a,b in zip(p,q))
   reports[name]={'native':native,'eevee':eevee,'max_byte_error':error}
   checks[name+'_matches_native_display']=error<=3
   capture_error=max(abs(a-b) for p,q in zip(state['files']['eevee_'+name],state['files']['native_'+name]) for a,b in zip(p,q))
   reports[name]['capture_max_byte_error']=capture_error
   checks[name+'_capture_matches_native_output']=capture_error<=3
  checks['native_ocio_used']=c.engine.last_response['eevee_state']['color_management']['native_ocio']
  window=settings_window.SettingsWindow(c)
  checks['hdri_quality_control_visible']=cmds.optionMenu(window.reflection_quality,query=True,value=True)=='2048'
  window.set_hdri_resolution('4096');snap('high_reflection')
  checks['reflection_4096_applied']=c.engine.last_response['eevee_state']['environment']['probe_resolution']=='4096'
  old_session=c.engine.session
  cmds.colorManagementPrefs(edit=True,renderingSpaceName='scene-linear Rec.709-sRGB')
  snap('changed_working_space')
  checks['working_space_change_restarts_worker']=c.engine.session!=old_session and c.engine.last_response['eevee_state']['color_management']['working_space']=='scene-linear Rec.709-sRGB'
  checks['gpu_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())
def start():
 global timer
 cmds.file(new=True,force=True)
 mel.eval('setNamedPanelLayout "Single Perspective View"')
 for x,color in zip((-3,0,3),((.18,.18,.18),(.8,.02,.01),(4,2,.5))):
  p=cmds.polyPlane(width=2,height=2,axis=(0,0,1))[0];cmds.setAttr(p+'.translateX',x)
  m=cmds.shadingNode('standardSurface',asShader=True);cmds.setAttr(m+'.base',0);cmds.setAttr(m+'.specular',0)
  cmds.setAttr(m+'.emission',1);cmds.setAttr(m+'.emissionColor',*color,type='double3')
  sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(m+'.outColor',sg+'.surfaceShader');cmds.sets(p,edit=True,forceElement=sg)
 cmds.setAttr('persp.translate',0,0,15,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3');cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',10)
 cmds.modelPanel('modelPanel4',edit=True,camera='persp')
 cmds.modelEditor('modelPanel4',edit=True,displayLights='default',grid=False,shadows=False,depthOfFieldPreview=False,displayAppearance='smoothShaded',displayTextures=True,selectionHiliteDisplay=False)
 cmds.setAttr('hardwareRenderingGlobals.ssaoEnable',False);cmds.setAttr('hardwareRenderingGlobals.bloomEnable',False)
 cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
 cmds.setAttr(ui.scene_settings(select=False)+'.volumetrics',False)
 state['c']=c;timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(200)
def safe():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
