"""Prism video regression on an explicitly supplied production scene, never saved."""
import ast,copy,hashlib,json,logging,os,sys,time,traceback,types,typing,subprocess
from collections import OrderedDict
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as api
import maya.OpenMayaUI as OpenMayaUI
import maya.utils
from PySide2 import QtCore,QtGui,QtWidgets
ROOT=Path(__file__).resolve().parents[2];OUTPUT=Path(os.environ['EEVEE_PRISM_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUTPUT/'prism_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT))
sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport,prism_capture,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);SOURCE_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FFMPEG=os.environ['EEVEE_PRISM_FFMPEG'];checks={};reports={};state={'deadline':time.monotonic()+600};timer=None
START=int(os.environ.get('EEVEE_PRISM_RANGE_START',1));END=int(os.environ.get('EEVEE_PRISM_RANGE_END',12))


def methods(path,names,scope):
 tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'))
 for cls in tree.body:
  if not isinstance(cls,ast.ClassDef):continue
  for node in cls.body:
   if isinstance(node,ast.FunctionDef) and node.name in names:
    node=copy.deepcopy(node);node.decorator_list=[]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),scope)
 return {name:scope[name] for name in names}


def decode(path):
 result=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-vf','scale=160:90','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,timeout=60)
 if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace'))
 size=160*90*3
 return [result.stdout[i:i+size] for i in range(0,len(result.stdout),size)]


def finish(error=None):
 if timer:timer.stop()
 checks['source_scene_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SOURCE_SHA
 (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 prism_capture.unbind();ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def run():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  scope=dict(vars(typing),cmds=cmds,mel=mel,api=api,OpenMayaUI=OpenMayaUI,os=os,logger=logging.getLogger('PrismProbe'))
  functions=methods(os.environ['EEVEE_PRISM_MAYA_FUNCTIONS'],['sm_playblast_createPlayblast','sm_playblast_postExecute'],scope)
  media_scope=dict(vars(typing),os=os,OrderedDict=OrderedDict,re=__import__('re'),glob=__import__('glob'),platform=__import__('platform'),subprocess=subprocess,logger=logging.getLogger('PrismMediaProbe'),sys=sys)
  convert=methods(os.environ['EEVEE_PRISM_MEDIA_MANAGER'],['convertMedia'],media_scope)['convertMedia']
  fps=1/api.MTime(1,api.MTime.uiUnit()).asUnits(api.MTime.kSeconds)
  core=types.SimpleNamespace(uiAvailable=True,framePadding=4,prismIni='',getConfig=lambda *a,**k:k.get('dft'),getFPS=lambda:fps,popup=lambda *a,**k:reports.setdefault('popups',[]).append(str(a)))
  media=types.SimpleNamespace(core=core,videoFormats=['.avi','.mp4','.mov'],getFFmpeg=lambda **k:FFMPEG,getMediaResolution=lambda p:{'width':1920,'height':1080})
  media.convertMedia=types.MethodType(convert,media);core.media=media
  plugin=types.SimpleNamespace(core=core,playblastSettings={'imageFormat':8,'filmFit':1,'displayFilmGate':False,'displayResolution':False,'overscan':1},isNodeValid=lambda o,n:cmds.objExists(n))
  for name,method in functions.items():setattr(plugin,name,types.MethodType(method,plugin))
  core.appPlugin=plugin;prism_capture.bind(core)
  origin=types.SimpleNamespace(curCam=state['camera'],cb_formats=QtWidgets.QComboBox(),chb_useRecommendedSettings=QtWidgets.QCheckBox(),chb_resOverride=QtWidgets.QCheckBox(),sp_resWidth=QtWidgets.QSpinBox(),sp_resHeight=QtWidgets.QSpinBox(),updateLastPath=lambda p:state.update(last_path=p))
  origin.chb_useRecommendedSettings.setChecked(True);origin.chb_resOverride.setChecked(True)
  for widget,value in ((origin.sp_resWidth,1920),(origin.sp_resHeight,1080)):widget.setMaximum(4096);widget.setValue(value)
  origin.cb_formats.addItems(['.mp4','.qt (with audio)'])
  sample_frames=[START,(START+END)//2,END]
  for label,fmt in [('mp4','.mp4'),('mov','.qt (with audio)')]:
   folder=OUTPUT/label;folder.mkdir();(folder/'metadata.json').write_text('{}');origin.cb_formats.setCurrentText(fmt);state.pop('last_path',None)
   cmds.setFocus('modelPanel1');started=time.monotonic();plugin.sm_playblast_createPlayblast(origin,[START,END],str(folder/'preview.####.jpg'))
   trace=list(c.capture_records);checks[label+'_all_poses']=[r['maya_frame'] for r in trace]==list(range(START,END+1));checks[label+'_all_full_hd']=all((r['width'],r['height'])==(1920,1080) for r in trace)
   checks[label+'_rig_deformations_captured']=sum(r['deformed_meshes'] for r in trace)>1
   if label=='mp4':media.convertMedia(str(folder/'preview.%04d.jpg'),START,str(folder/'preview.mp4'),settings={'-framerate':fps});path=folder/'preview.mp4'
   else:path=Path(state['last_path'])
   frames=decode(path);checks[label+'_encoded_frame_count']=len(frames)==END-START+1
   checks[label+'_video_contains_motion']=len(set(frames))>max(2,(END-START+1)//2)
   errors=[]
   for frame in sample_frames:
    cmds.playblast(format='image',compression='png',startTime=frame,endTime=frame,filename=str(folder/('reference_'+str(frame))),viewer=False,forceOverwrite=True,percent=100,widthHeight=(1920,1080),showOrnaments=True,offScreen=True,editorPanelName=c.panel)
    reference=decode(next(folder.glob('reference_'+str(frame)+'.*.png')))[0];actual=frames[frame-START]
    error=(sum((a-b)**2 for a,b in zip(actual,reference))/len(actual))**.5;errors.append(error)
   checks[label+'_matches_independent_reference_frames']=max(errors)<12
   reports[label]={'frame_count':len(frames),'distinct_frames':len(set(frames)),'reference_frames':sample_frames,'reference_rgb_rmse':errors,'seconds':time.monotonic()-started,'deformed_mesh_samples':sum(r['deformed_meshes'] for r in trace),'capture_records':len(trace)}
   plugin.sm_playblast_postExecute(origin)
  checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None;finish()
 except Exception:finish(traceback.format_exc())


def start():
 def stage(name):
  (OUTPUT/'startup-stage.json').write_text(json.dumps({'stage':name,'time':time.time()}))
 stage('begin')
 def observe_modal():
  widget=QtWidgets.QApplication.activeModalWidget()
  (OUTPUT/'startup-windows.json').write_text(json.dumps({'titles':[w.windowTitle() for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()],'modal':widget.windowTitle() if widget else None},indent=2))
  if widget is not None:
   labels=[n.text() for n in widget.findChildren(QtWidgets.QLabel)]
   (OUTPUT/'startup-modal.json').write_text(json.dumps({'title':widget.windowTitle(),'class':type(widget).__name__,'labels':labels},indent=2))
   widget.grab().save(str(OUTPUT/'startup-modal.png'))
   # Only approve the bridge we are testing, in this owned profile. Leave all
   # other plugin/file security prompts intact and record them for diagnosis.
   if widget.windowTitle()=='Untrusted Plugin Loading - Security Warning' and any(
       '<b>eeveeBridge.py</b>' in text and (BRIDGE/'plug-ins').as_posix() in text for text in labels):
    button=next((b for b in widget.findChildren(QtWidgets.QPushButton) if b.text().replace('&','')=='Allow'),None)
    if button:button.click()
 observer=QtCore.QTimer();observer.timeout.connect(observe_modal);observer.start(1000);state['startup_observer']=observer
 # This supplied scene may require eeveeBridge. Trust only the tested plugin's
 # exact folder in this disposable profile, before loading that requirement.
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True)
 stage('bridge_loaded')
 cmds.loadPlugin('mtoa',quiet=True)
 stage('mtoa_loaded')
 cmds.file(SOURCE.as_posix(),open=True,force=True,prompt=False,executeScriptNodes=False)
 after_load()

def after_load():
 global timer
 (OUTPUT/'startup-stage.json').write_text(json.dumps({'stage':'scene_loaded','time':time.time()}))
 state['startup_observer'].stop();mel.eval('setNamedPanelLayout "Four View"')
 cameras=[n for n in cmds.ls(type='camera',long=True) if not cmds.camera(n,query=True,startupCamera=True)];camera=cameras[0] if cameras else 'persp'
 cmds.modelPanel('modelPanel4',edit=True,camera=camera);cmds.modelEditor('modelPanel4',edit=True,displayLights='default',grid=False,shadows=False,displayAppearance='smoothShaded',displayTextures=True,lights=False,cameras=False,nurbsCurves=False,manipulators=False,selectionHiliteDisplay=False)
 cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
 state.update(controller=c,camera=camera);timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(200)

def safe_start():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe_start)
