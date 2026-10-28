"""Exercise the installed Prism Maya playblast method without publishing media."""
import ast,copy,hashlib,json,logging,os,sys,time,traceback,types,typing,subprocess,wave,math,struct
from collections import OrderedDict
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as api
import maya.OpenMayaUI as OpenMayaUI
import maya.utils
from PySide2 import QtCore,QtGui,QtWidgets
ROOT=Path(__file__).resolve().parents[2];OUTPUT=Path(os.environ['EEVEE_PRISM_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUTPUT/'prism_regression_profile':raise RuntimeError('Owned Maya profile required')
sys.path.insert(0,str(Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT))/'scripts'))
from eevee_maya import ui,viewport,__version__
FFMPEG=os.environ['EEVEE_PRISM_FFMPEG'];checks={};reports={};state={'deadline':time.monotonic()+240};timer=None


def installed_methods(path,names,namespace):
 tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'))
 for cls in tree.body:
  if not isinstance(cls,ast.ClassDef):continue
  for node in cls.body:
   if isinstance(node,ast.FunctionDef) and node.name in names:
    node=copy.deepcopy(node);node.decorator_list=[]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),namespace)
 return {name:namespace[name] for name in names}


def decode(path,label):
 r=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-vf','scale=160:90','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,timeout=40)
 if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace'))
 frame_bytes=160*90*3;frames=[r.stdout[i:i+frame_bytes] for i in range(0,len(r.stdout),frame_bytes)];centers=[]
 for frame in frames:
  ids=[i//3 for i in range(0,len(frame),3) if frame[i]>80 and frame[i]>frame[i+1]*1.5 and frame[i]>frame[i+2]*1.5]
  centers.append(sum(i%160 for i in ids)/max(1,len(ids)))
  checks[label+'_visible_geometry']=checks.get(label+'_visible_geometry',True) and len(ids)>20
 checks[label+'_three_video_frames']=len(frames)==3
 checks[label+'_three_distinct_poses']=len(frames)==3 and centers[0]+15<centers[1] and centers[1]+15<centers[2]
 if label in ('avi_iyuv','mp4_audio','quicktime'):
  audio=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le','-'],capture_output=True,timeout=40)
  samples=[x[0] for x in struct.iter_unpack('<h',audio.stdout)]
  checks[label+'_audible_audio_preserved']=audio.returncode==0 and len(samples)>3000 and max(map(abs,samples),default=0)>1000
 return {'frame_count':len(frames),'centroid_x':centers,'unique_frames':len({hashlib.sha256(f).hexdigest() for f in frames})}


def finish(error=None):
 if timer:timer.stop()
 (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def run():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
 if not os.environ.get('EEVEE_PRISM_COLD') and (not c.presented_once or c.force or not c.engine.available):return
 timer.stop()
 try:
  if os.environ.get('EEVEE_PRISM_DEBUG'):
   from eevee_maya import capture
   events=reports['events']=[];execute=viewport.CameraSync.execute;command=cmds.playblast
   def debug_execute(self,context):
    if len(events)<1000:events.append({'operation':'camera_sync','active':capture.active(),'destination':self.owner.destination,'panel':c.panel,'same_controller':ui._controller is c,'frame':cmds.currentTime(query=True),'size':list(context.getViewportDimensions()[2:])})
    return execute(self,context)
   def debug_command(*args,**kwargs):
    events.append({'operation':'playblast','options':kwargs,'panel':c.panel,'override':cmds.modelEditor(c.panel,query=True,rendererOverrideName=True)})
    result=command(*args,**kwargs);events.append({'operation':'returned','trace':list(c.capture_records)});return result
   viewport.CameraSync.execute=debug_execute;cmds.playblast=debug_command
  namespace=dict(vars(typing),cmds=cmds,mel=mel,api=api,OpenMayaUI=OpenMayaUI,os=os,logger=logging.getLogger('PrismProbe'))
  methods=installed_methods(os.environ['EEVEE_PRISM_MAYA_FUNCTIONS'],['sm_playblast_createPlayblast','sm_playblast_postExecute'],namespace)
  media_ns=dict(vars(typing),os=os,OrderedDict=OrderedDict,re=__import__('re'),glob=__import__('glob'),platform=__import__('platform'),subprocess=subprocess,logger=logging.getLogger('PrismMediaProbe'),sys=sys)
  media_method=installed_methods(os.environ['EEVEE_PRISM_MEDIA_MANAGER'],['convertMedia'],media_ns)['convertMedia']
  core=types.SimpleNamespace(uiAvailable=True,framePadding=4,prismIni='',getConfig=lambda *a,**k:k.get('dft'),getFPS=lambda:24,popup=lambda *a,**k:reports.setdefault('popups',[]).append(str(a)))
  media=types.SimpleNamespace(core=core,videoFormats=['.avi','.mp4','.mov'],getFFmpeg=lambda **k:FFMPEG,getMediaResolution=lambda p:{'width':1920,'height':1080})
  media.convertMedia=types.MethodType(media_method,media);core.media=media
  plugin=types.SimpleNamespace(core=core,playblastSettings={'imageFormat':8,'filmFit':1,'displayFilmGate':False,'displayResolution':False,'overscan':1},isNodeValid=lambda o,n:cmds.objExists(n))
  for name,method in methods.items():setattr(plugin,name,types.MethodType(method,plugin))
  core.appPlugin=plugin
  if os.environ.get('EEVEE_PRISM_ADAPTER'):
   from eevee_maya import prism_capture
   sys.modules['PrismInit']=types.SimpleNamespace(pcore=core);prism_capture.install()
   checks['prism_adapter_bound']=prism_capture._binding is not None and prism_capture._binding[0] is plugin
  reports['audio_fixture']={'slider_sound':cmds.timeControl(mel.eval('$tmpVar=$gPlayBackSlider'),query=True,sound=True),'node':state.get('sound'),'filename':cmds.getAttr(state['sound']+'.filename'),'end_frame':cmds.getAttr(state['sound']+'.endFrame')}
  origin=types.SimpleNamespace(curCam='persp',cb_formats=QtWidgets.QComboBox(),chb_useRecommendedSettings=QtWidgets.QCheckBox(),chb_resOverride=QtWidgets.QCheckBox(),sp_resWidth=QtWidgets.QSpinBox(),sp_resHeight=QtWidgets.QSpinBox(),updateLastPath=lambda p:state.update(last_path=p))
  origin.chb_useRecommendedSettings.setChecked(True);origin.chb_resOverride.setChecked(True)
  for widget,value in ((origin.sp_resWidth,1920),(origin.sp_resHeight,1080)):widget.setMaximum(4096);widget.setValue(value)
  origin.cb_formats.addItems(['.mp4','.avi (with audio)','.mp4 (with audio)','.qt (with audio)'])
  for label,fmt in [('mp4_sequence','.mp4'),('avi_iyuv','.avi (with audio)'),('mp4_audio','.mp4 (with audio)'),('quicktime','.qt (with audio)')]:
   folder=OUTPUT/label;folder.mkdir();(folder/'metadata.json').write_text('{}')
   origin.cb_formats.setCurrentText(fmt);cmds.setFocus(os.environ.get('EEVEE_PRISM_FOCUS_PANEL',c.panel));state.pop('last_path',None);c.capture_records=[]
   plugin.sm_playblast_createPlayblast(origin,[1,3],str(folder/'preview.####.jpg'))
   trace=list(c.capture_records);reports[label]={'trace':trace,'capture_error':c.capture_error,'gpu_error':viewport._override.gpu_image.error}
   if fmt=='.mp4':
    converted=media.convertMedia(str(folder/'preview.%04d.jpg'),1,str(folder/'preview.mp4'),settings={'-framerate':24});path=folder/'preview.mp4'
    reports[label]['conversion_stderr']=converted[1][-1000:] if converted else None
   else:path=Path(state.get('last_path','missing'))
   reports[label]['files']=[p.name for p in folder.iterdir()]
   checks[label+'_exact_pose_trace']=[r['maya_frame'] for r in trace]==[1,2,3]
   checks[label+'_capture_error_free']=c.capture_error is None
   checks[label+'_skin_deformations_synchronized']=sum(r['deformed_meshes'] for r in trace)>1
   if path.is_file():reports[label]['decoded']=decode(path,label)
   else:checks[label+'_output_exists']=False
   plugin.sm_playblast_postExecute(origin)
  if os.environ.get('EEVEE_PRISM_ADAPTER'):
   original_command=cmds.playblast
   prism_capture.unbind();checks['prism_original_method_restored']=plugin.sm_playblast_createPlayblast.__func__ is methods['sm_playblast_createPlayblast']
   checks['native_playblast_command_restored']=cmds.playblast is original_command
  finish()
 except Exception:finish(traceback.format_exc())


def start():
 global timer
 cmds.file(new=True,force=True)
 if os.environ.get('EEVEE_PRISM_FOCUS_PANEL'):mel.eval('setNamedPanelLayout "Four View"')
 obj=cmds.polyCube(height=2,subdivisionsHeight=4)[0];cmds.setAttr(obj+'.translateY',1)
 cmds.select(clear=True);joint=cmds.joint(position=(0,0,0));tip=cmds.joint(position=(0,1,0));cmds.skinCluster(joint,tip,obj,toSelectedBones=True)
 material=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(material+'.color',0,0,0,type='double3');cmds.setAttr(material+'.incandescence',1,0,0,type='double3')
 sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(material+'.outColor',sg+'.surfaceShader');cmds.sets(obj,edit=True,forceElement=sg)
 for frame,x in ((1,-3),(2,0),(3,3)):
  cmds.setKeyframe(joint,attribute='translateX',time=frame,value=x);cmds.setKeyframe(tip,attribute='rotateZ',time=frame,value=(frame-2)*10)
  cmds.setKeyframe('persp',attribute='translateX',time=frame,value=(frame-1)*.05)
 audio_path=OUTPUT/'tone.wav'
 with wave.open(str(audio_path),'wb') as audio:
  audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000)
  audio.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(i*2*math.pi*880/48000))) for i in range(24000)))
 sound=cmds.sound(file=str(audio_path.resolve()),offset=1);cmds.timeControl(mel.eval('$tmpVar=$gPlayBackSlider'),edit=True,sound=sound,displaySound=True);state['sound']=sound
 cmds.setAttr('persp.translate',0,0,12,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3');cmds.modelPanel('modelPanel4',edit=True,camera='persp')
 cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,displayAppearance='smoothShaded',cameras=False,lights=False,manipulators=False,selectionHiliteDisplay=False)
 cmds.currentTime(1);cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
 state['controller']=c;timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(150)

def safe_start():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe_start)
