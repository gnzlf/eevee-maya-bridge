"""Owned comparison on a user-supplied source; never save or publish assets."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
from PySide2 import QtCore,QtWidgets
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_LOOK_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'looks_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport,exporter,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
MATERIAL_PREFIX=os.environ.get('EEVEE_PROBE_MATERIAL_PREFIX','')
state={'deadline':time.monotonic()+540};checks={};reports={};timer=None
def finish(error=None):
 if timer:timer.stop()
 checks['source_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
 (OUT/'result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'version':__version__,'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2),encoding='utf-8')
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))
def snap(name):
 start=time.monotonic()
 cmds.playblast(format='image',compression='png',startTime=148,endTime=148,filename=str(OUT/name),viewer=False,forceOverwrite=True,percent=100,widthHeight=(1920,1080),showOrnaments=False,offScreen=True,editorPanelName='modelPanel4')
 reports[name]={'seconds':time.monotonic()-start}
def run():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Timeout: '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  snap('eevee_default');checks['default_capture_valid']=not c.capture_error
  reports['default_state']=c.engine.last_response.get('eevee_state')
  cmds.modelEditor(c.panel,edit=True,displayLights='all');c.force=True
  snap('eevee_hdri');checks['hdri_capture_valid']=not c.capture_error
  reports['hdri_state']=c.engine.last_response.get('eevee_state')
  if os.environ.get('EEVEE_VERIFY_MATERIALS')=='1':
   specs=[exporter.material(n) for n in cmds.ls(materials=True) if n.startswith(MATERIAL_PREFIX)]
   body=next(s for s in specs if s['name']==os.environ['EEVEE_PROBE_BODY_MATERIAL'])
   eye=next(s for s in specs if s['name']==os.environ['EEVEE_PROBE_EYE_MATERIAL'])
   checks['body_layered_texture_preserved']=body['color_texture']['baked']
   checks['body_procedural_bump_preserved']=body['normal_map']['texture']['baked'] and body['normal_map']['strength']==1
   checks['eye_layered_texture_preserved']=eye['color_texture']['baked']
   checks['native_input_ocio_used']=reports['hdri_state']['color_management']['native_ocio']
   checks['single_native_display_transform']=reports['hdri_state']['color_management']['display_owner']=='Maya'
   checks['hdri_reflection_resolution_2048']=reports['hdri_state']['environment']['probe_resolution']=='2048'
   cmds.setAttr(ui.scene_settings(select=False)+'.volumetrics',False);snap('eevee_hdri_clear')
  specs=[exporter.material(n) for n in cmds.ls(materials=True) if n.startswith(MATERIAL_PREFIX)]
  (OUT/'material-specs.json').write_text(json.dumps(specs,indent=2),encoding='utf-8')
  checks['gpu_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())
def start():
 global timer
 def observe():
  w=QtWidgets.QApplication.activeModalWidget()
  if not w:return
  labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
  (OUT/'modal.json').write_text(json.dumps({'title':w.windowTitle(),'labels':labels},indent=2))
  if w.windowTitle()=='Untrusted Plugin Loading - Security Warning' and any('<b>eeveeBridge.py</b>' in t and (BRIDGE/'plug-ins').as_posix() in t for t in labels):
   b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','')=='Allow'),None)
   if b:b.click()
 observer=QtCore.QTimer();observer.timeout.connect(observe);observer.start(500);state['observer']=observer
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True);cmds.loadPlugin('mtoa',quiet=True)
 cmds.file(SOURCE.as_posix(),open=True,force=True,prompt=False,executeScriptNodes=False);observer.stop()
 ui.stop();mel.eval('setNamedPanelLayout "Single Perspective View"')
 cmds.currentTime(148,edit=True)
 cmds.modelPanel('modelPanel4',edit=True,camera='camera1')
 cmds.modelEditor('modelPanel4',edit=True,rendererOverrideName='',displayLights='default',grid=False,shadows=False,displayAppearance='smoothShaded',displayTextures=True,lights=False,cameras=False,nurbsCurves=False,manipulators=False,selectionHiliteDisplay=False,depthOfFieldPreview=False)
 cmds.setAttr('hardwareRenderingGlobals.ssaoEnable',False);cmds.setAttr('hardwareRenderingGlobals.bloomEnable',False)
 cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',True);cmds.setAttr('hardwareRenderingGlobals.multiSampleCount',8)
 cmds.select(clear=True);snap('native_default')
 viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=960,adaptive_quality=False)
 state['controller']=c;timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(200)
def safe():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
