"""Interaction optimisation probe on the production layout, in an owned Maya profile.

Phases (5 s each, separated by a settle so the final quality is recovered):
  camera_translate  same input as tests/test_camera_controlled.py (comparable
                    with diagnostics/camera_navigation_controlled.json)
  camera_orbit      camera tumble around the centre of interest
  light_move        a scene light rotated every 16 ms
  rig_playback      real Maya playback (cmds.play) of the shot's animation
After each phase the menu's performance report (diagnostics_ui.collect_performance)
is saved without the file dialog. Idle submissions are counted between phases.
The source scene is never saved.
"""
import hashlib,json,math,os,shutil,statistics,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.OpenMayaUI as qtui
from PySide2 import QtCore,QtWidgets
from shiboken2 import wrapInstance
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
PANEL='eeveeInteractionModelPanel'
from eevee_maya import ui,viewport,diagnostics,diagnostics_ui,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PHASES=['camera_translate','camera_orbit','light_move','rig_playback']
DURATION=5.0
S={'deadline':time.monotonic()+900,'phase':-1,'started':None,'records':[],'reports':{},'idle':[],'inputs':[],'checks':{},'previous':0}
timers={}

def log(msg):
 with open(OUT/'probe.log','a',encoding='utf-8') as f:f.write('%.3f %s\n'%(time.monotonic(),msg))

def copy_logs():
 c=S.get('c')
 if c is None:return
 for name in ('blender.log','maya_error.txt'):
  p=Path(c.engine.session)/name
  if p.exists():shutil.copy(p,OUT/name)

def finish(error=None):
 for t in timers.values():t.stop()
 try:
  if cmds.play(query=True,state=True):cmds.play(state=False)
 except Exception:pass
 if error:log('ERROR '+error)
 S['checks']['source_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
 c=S.get('c')
 if c is not None:
  S['checks']['gpu_error_free']=viewport._override.gpu_image.error is None
  S['checks']['no_maya_error']=not (Path(c.engine.session)/'maya_error.txt').exists()
 copy_logs()
 result={'version':__version__,'error':error,'checks':S['checks'],'records':S['records'],'idle':S['idle'],
         'meshes':len(c.mesh_names) if c else None,'config':{k:c.engine.config.get(k) for k in ('interaction_samples','settle_seconds','idle_poll_ms','interaction_width','navigation_width','max_width')} if c else None,
         'session':str(c.engine.session) if c else None,'pid':os.getpid()}
 (OUT/'result.json').write_text(json.dumps(result,indent=2))
 try:ui.stop();ui.remove_menu();viewport.deregister()
 except Exception:log(traceback.format_exc())
 QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))

def presented_hook():
 image=viewport.register().gpu_image;original=image.execute
 def draw(context):
  original(context)
  if S['started'] is None:return
  frame=image.frame
  if frame and image.displayed_id!=S['previous']:
   S['previous']=image.displayed_id;now=time.perf_counter()
   req=next((r for r in reversed(S['c'].engine.request_history) if r['id']==frame['id']),None)
   if req is None:return
   sub=req['submitted_at'];ins=[t for t in S['inputs'] if t<=sub]
   if ins:S['samples'].append({'latency_ms':(now-ins[-1])*1000,'id':frame['id'],'time':now,'maya_frame':frame.get('maya_frame')})
 image.execute=draw

def phase_report(name,elapsed):
 c=S['c'];orig=diagnostics.performance_report
 diagnostics.performance_report=lambda *a,**k:orig(*a,window_seconds=elapsed+.05)
 try:report=diagnostics_ui.collect_performance(c,viewport._override)
 finally:diagnostics.performance_report=orig
 report['phase']=name
 (OUT/('performance_'+name+'.json')).write_text(json.dumps(report,indent=2))
 return report

def record(name,now):
 c=S['c'];values=S['samples'];lat=[v['latency_ms'] for v in values]
 hist=[r for r in c.engine.history if r.get('finished_at',0)>=S['started']];keys={k for r in hist for k in r.get('timings_ms',{})}
 rep=phase_report(name,now-S['started'])
 rec={'requested_width':c.engine.config['max_width'],'mode':name,'maya_frame':cmds.currentTime(query=True),'presented':len(values),
  'input_events':len(S['inputs']),'median_latency_ms':statistics.median(lat) if lat else None,
  'p95_latency_ms':sorted(lat)[int((len(lat)-1)*.95)] if lat else None,'fps':len(values)/(now-S['started']),
  'worker_ms':{k:statistics.mean(r['timings_ms'].get(k,0) for r in hist) for k in keys},'maya_timings':dict(c.timings),
  'aa_samples':statistics.median([f['samples'] for f in rep['frames'] if f.get('samples') is not None] or [0]),
  'actual_width':statistics.median([f['width'] for f in rep['frames'] if f.get('width')] or [0]),
  'unique_maya_frames':len({v['maya_frame'] for v in values}),'submitted':c.engine.sent_id-S['sent0'],
  'report_fps':rep['new_gpu_frames_per_second_in_sample'],'report_submit_to_draw_ms':rep['submit_to_draw_ms']}
 rec['median_worker_seconds_ms']=statistics.median([r['seconds']*1000 for r in hist] or [0])
 rec['median_submit_to_receive_ms']=statistics.median([r['received_at']-r['submitted_at'] for r in hist if r.get('submitted_at')] or [0])*1000 if hist and 'submitted_at' in hist[0] else None
 if name=='rig_playback':rec['maya_frames_per_second']=len(S['inputs'])/(now-S['started'])
 S['records'].append(rec);log('record '+json.dumps(rec)[:400])

def drive(name,i):
 st=S
 if name=='camera_translate':
  cmds.setAttr(st['camera']+'.translateX',st['basex']+i*.04)
 elif name=='camera_orbit':
  cmds.setAttr(st['pivot']+'.rotateY',i*.5)
 elif name=='light_move':
  cmds.setAttr(st['light_parent']+'.rotateY',st['light_ry']+math.sin(i*.08)*20)
 st['inputs'].append(time.perf_counter())
 st['view'].refresh(False,True)

def on_input():
 try:
  name=PHASES[S['phase']];S['index']+=1;drive(name,S['index'])
 except Exception:finish(traceback.format_exc())

def start_phase(name):
 c=S['c'];log('start '+name);c.engine.history.clear()
 S.update(started=time.perf_counter(),inputs=[],samples=[],index=0,sent0=c.engine.sent_id)
 if name in ('camera_orbit','camera_translate'):
  cmds.modelPanel(c.panel,edit=True,camera=S['orbit_cam' if name=='camera_orbit' else 'camera'])
 if name=='rig_playback':
  cmds.currentTime(S['range'][0]);S['frame_times']=[]
  S['job']=om.MEventMessage.addEventCallback('timeChanged',lambda *a:S['inputs'].append(time.perf_counter()))
  cmds.play(forward=True)
 else:timers['input'].start(16)

def end_phase(name,now):
 timers['input'].stop()
 if name=='rig_playback':
  cmds.play(state=False);om.MMessage.removeCallback(S.pop('job'))
  S['rig_frames_advanced']=len(S['inputs'])
 record(name,now)
 if name=='camera_orbit':cmds.modelPanel(S['c'].panel,edit=True,camera=S['camera'])
 S.update(started=None,settle=time.monotonic(),idle_sent=None)

def tick():
 try:
  c=S['c'];now=time.perf_counter()
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:2000])
  if time.monotonic()-S.get('heartbeat',0)>1:
   S['heartbeat']=time.monotonic()
   (OUT/'progress.json').write_text(json.dumps({'phase':S['phase'],'sent':c.engine.sent_id,'received':c.engine.received_id,'status':c.engine.status,'force':c.force}))
  if S['started'] is not None:
   if now-S['started']>=DURATION:end_phase(PHASES[S['phase']],now)
   return
  # Settled: wait for the full-quality frame, then measure 2 s of idle.
  if not c.presented_once or c.force or c.engine.received_id!=c.engine.sent_id:return
  if time.monotonic()-S.get('settle',0)<1.0:return
  if S.get('idle_sent') is None:S.update(idle_sent=c.engine.sent_id,idle_at=time.monotonic(),idle_exports=c.timings.get('export_ms'));return
  if time.monotonic()-S['idle_at']<2.0:return
  S['idle'].append({'after_phase':PHASES[S['phase']] if S['phase']>=0 else 'startup','seconds':time.monotonic()-S['idle_at'],
   'submissions':c.engine.sent_id-S['idle_sent'],'last_width':c.engine.last_response.get('width'),
   'last_samples':(c.engine.last_response.get('eevee_state') or {}).get('samples')})
  log('idle '+json.dumps(S['idle'][-1]))
  if S['phase']>=0:S['checks']['restores_full_quality_after_'+PHASES[S['phase']]]=c.engine.last_response.get('width')==1920
  S['phase']+=1;S['idle_sent']=None
  if S['phase']==len(PHASES):finish();return
  start_phase(PHASES[S['phase']])
 except Exception:finish(traceback.format_exc())

def setup():
 def modal():
  w=QtWidgets.QApplication.activeModalWidget()
  if w:
   labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
   (OUT/'modal.json').write_text(json.dumps({'title':w.windowTitle(),'labels':labels}))
   b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','') in ('Allow','Allow All')),None)
   if b and 'eeveeBridge' in ' '.join(labels):b.click()
 observer=QtCore.QTimer();observer.timeout.connect(modal);observer.start(500);timers['observer']=observer
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True)
 try:cmds.loadPlugin('mtoa',quiet=True)
 except Exception:log('mtoa not loaded')
 cmds.file(SOURCE.as_posix(),open=True,force=True,prompt=False,executeScriptNodes=False);observer.stop();ui.stop()
 log('scene opened')
 mel.eval('setNamedPanelLayout "Single Perspective View"')
 cmds.modelEditor('modelPanel4',edit=True,allObjects=False,grid=False)
 window=cmds.window('eeveeInteractionTestWindow',widthHeight=(1280,800))
 cmds.paneLayout(configuration='single');cmds.modelPanel(PANEL,menuBarVisible=False);cmds.showWindow(window)
 cameras=[n for n in cmds.ls(type='camera',long=True) if not cmds.camera(n,query=True,startupCamera=True)]
 src=cameras[0] if cameras else 'perspShape'
 sl=om.MSelectionList();sl.add(src);path=sl.getDagPath(0)
 camera,shape=cmds.camera(name='NavigationCam');cmds.xform(camera,worldSpace=True,matrix=list(path.inclusiveMatrix()))
 for attr in ('focalLength','horizontalFilmAperture','verticalFilmAperture','filmFit','nearClipPlane','farClipPlane'):
  cmds.setAttr(shape+'.'+attr,cmds.getAttr(path.fullPathName()+'.'+attr))
 # Orbit rig: a duplicate camera parented under a pivot at the centre of interest.
 coi=cmds.getAttr(path.fullPathName()+'.centerOfInterest');m=om.MMatrix(path.inclusiveMatrix())
 eye=om.MPoint(0,0,0)*m;fwd=om.MVector(0,0,-1)*m;target=eye+fwd.normal()*coi
 pivot=cmds.group(empty=True,name='NavigationPivot');cmds.xform(pivot,worldSpace=True,translation=(target.x,target.y,target.z))
 orbit=cmds.duplicate(camera,name='OrbitCam')[0];orbit=cmds.parent(orbit,pivot)[0]
 cmds.modelPanel(PANEL,edit=True,camera=camera)
 # Same viewport quality as camera_navigation_controlled.json.
 cmds.modelEditor(PANEL,edit=True,displayLights='all',displayAppearance='smoothShaded',displayTextures=True,shadows=True,grid=False,nurbsCurves=False,lights=False,manipulators=False,selectionHiliteDisplay=False,depthOfFieldPreview=True)
 for attr,value in [('ssaoEnable',True),('multiSampleEnable',True),('multiSampleCount',8),('bloomEnable',True),('renderDepthOfField',True)]:cmds.setAttr('hardwareRenderingGlobals.'+attr,value)
 for s in (shape,cmds.listRelatives(orbit,shapes=True,fullPath=True)[0]):cmds.setAttr(s+'.depthOfField',True);cmds.setAttr(s+'.focusDistance',280)
 view=omui.M3dView.getM3dViewFromModelPanel(PANEL)
 widget=wrapInstance(int(qtui.MQtUtil.findWindow(window)),QtWidgets.QWidget)
 for _ in range(2):
  QtWidgets.QApplication.processEvents();widget.resize(widget.width()+1280-view.portWidth(),widget.height()+720-view.portHeight())
 QtWidgets.QApplication.processEvents();cmds.setFocus(PANEL)
 lights=[cmds.listRelatives(l,parent=True,fullPath=True)[0] for l in cmds.ls(type=[t for t in ('spotLight','directionalLight','pointLight','areaLight','aiAreaLight') if t in cmds.allNodeTypes()],long=True) or []]
 movable=[l for l in lights if cmds.getAttr(l+'.rotateY',settable=True)]
 if movable:light_parent=movable[0];created=False
 else:
  light=cmds.spotLight(intensity=1);light_parent=cmds.listRelatives(light,parent=True,fullPath=True)[0];created=True
  cmds.setAttr(light_parent+'.translate',target.x,target.y+10,target.z+10,type='double3');cmds.setAttr(light_parent+'.rotateX',-45)
 curves=cmds.ls(type=['animCurveTL','animCurveTA','animCurveTU'])or[]
 rng=(cmds.playbackOptions(query=True,minTime=True),cmds.playbackOptions(query=True,maxTime=True))
 cmds.playbackOptions(loop='continuous');cmds.select(clear=True)
 info={'camera_source':src,'lights':len(lights),'moved_light':light_parent,'light_created':created,'anim_curves':len(curves),'range':rng,'fps':mel.eval('currentTimeUnitToFPS'),'port':[view.portWidth(),view.portHeight()]}
 (OUT/'scene_info.json').write_text(json.dumps(info,indent=2));log('scene '+json.dumps(info))
 S['checks']['scene_has_animation']=len(curves)>0
 S.update(view=view,range=rng)
 native_playback(lambda:attach_eevee(view,camera,orbit,pivot,light_parent,rng))

def native_playback(then):
 cmds.currentTime(S['range'][0]);times=[]
 cb=om.MEventMessage.addEventCallback('timeChanged',lambda *a:times.append(time.perf_counter()))
 t0=time.perf_counter();cmds.play(forward=True)
 def done():
  try:
   cmds.play(state=False);om.MMessage.removeCallback(cb);el=time.perf_counter()-t0
   d=[b-a for a,b in zip(times,times[1:])]
   S['records'].append({'mode':'rig_playback_viewport2','maya_frames':len(times),'maya_frames_per_second':len(times)/el,'median_frame_ms':statistics.median(d)*1000 if d else None,'p95_frame_ms':sorted(d)[int((len(d)-1)*.95)]*1000 if d else None,'playback_every_frame':cmds.playbackOptions(query=True,playbackSpeed=True)})
   log('record '+json.dumps(S['records'][-1]));cmds.currentTime(S['range'][0]);then()
  except Exception:finish(traceback.format_exc())
 QtCore.QTimer.singleShot(int(DURATION*1000),done)

def attach_eevee(view,camera,orbit,pivot,light_parent,rng):
 viewport.register();ui.install_menu();c=ui.attach(PANEL)
 node=ui.scene_settings(select=False);cmds.setAttr(node+'.volumetrics',True);cmds.setAttr(node+'.density',.002)
 c.engine.config.update(adaptive_quality=True,max_width=1920,fast_navigation=True)
 S.update(c=c,view=view,camera=camera,orbit_cam=orbit,pivot=pivot,basex=cmds.getAttr(camera+'.translateX'),
          light_parent=light_parent,light_ry=cmds.getAttr(light_parent+'.rotateY'),range=rng,settle=time.monotonic())
 presented_hook()
 timers['input']=QtCore.QTimer();timers['input'].timeout.connect(on_input)
 timers['tick']=QtCore.QTimer();timers['tick'].timeout.connect(tick);timers['tick'].start(50)

def safe():
 try:setup()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
