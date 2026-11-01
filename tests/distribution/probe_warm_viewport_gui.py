"""Owned Maya GUI: renderer/panel switches reuse one live Eevee scene."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore,QtGui

ROOT=Path(os.environ.get('EEVEE_INSTALLED_ROOT',Path(__file__).resolve().parents[2]))
OUT=Path(os.environ['EEVEE_WARM_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'warm_regression_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__
checks={};reports={};state={'phase':0,'deadline':time.monotonic()+360,'cycles':0};timer=None

def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'version':__version__,'passed':not error and all(checks.values()),
  'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))

def native_command(panel,eevee):
 cmds.setFocus(panel)
 menu=next(m for m in cmds.lsUI(menus=True,long=True) or [] if panel+'|' in m and 'buildRendererMenu' in str(cmds.menu(m,query=True,postMenuCommand=True)))
 mel.eval(cmds.menu(menu,query=True,postMenuCommand=True))
 item=next(i for i in cmds.menu(menu,query=True,itemArray=True)
  if (cmds.menuItem(i,query=True,label=True)=='Eevee' if eevee else i.rsplit('|',1)[-1]=='OGSRenderer'))
 mel.eval(cmds.menuItem(item,query=True,command=True))

def ready():
 c=ui._controller
 return c and not c.parked and c.presented_once and not c.force and c.engine.available and viewport.register().gpu_image.displayed_id==c.engine.received_id

def same_scene(label):
 c=ui._controller
 checks[label+'_same_controller']=c is state['c']
 checks[label+'_same_worker']=c.engine.process is state['process'] and c.engine.process.poll() is None
 checks[label+'_same_session']=str(c.engine.session)==state['session']
 checks[label+'_same_geometry_stream']=c.scene_stream is state['stream']
 checks[label+'_no_scene_rebuild']=c.engine.last_response.get('scene_rebuilds')==state['rebuilds']
 checks[label+'_gpu_error_free']=viewport.register().gpu_image.error is None

def new_panel():
 window=cmds.window(title='Owned Eevee warm-session test',widthHeight=(720,480));cmds.paneLayout()
 panel=cmds.modelPanel(camera=state['camera'],menuBarVisible=True)
 cmds.showWindow(window)
 cmds.modelEditor(panel,edit=True,displayAppearance='smoothShaded',displayLights='all',grid=False,selectionHiliteDisplay=False)
 return window,panel

def tick():
 try:
  (OUT/'progress.json').write_text(json.dumps({'phase':state['phase'],'cycles':state['cycles'],'time':time.time(),
   'parked':getattr(ui._controller,'parked',None),'sent':getattr(getattr(ui._controller,'engine',None),'sent_id',None)}))
  if time.monotonic()>state['deadline']:raise TimeoutError(str(getattr(getattr(ui._controller,'engine',None),'status',None)))
  phase=state['phase'];c=ui._controller
  if phase==0:
   if not ready():return
   state.update(c=c,process=c.engine.process,session=str(c.engine.session),stream=c.scene_stream,rebuilds=c.engine.last_response['scene_rebuilds'])
   checks['initial_scene_presented']=True
   native_command(c.panel,False);state.update(phase=1,paused_at=time.monotonic(),sent=c.engine.sent_id)
  elif phase==1:
   if not c or not c.parked:return
   if time.monotonic()-state['paused_at']<4.2:return
   checks['vp2_keeps_worker_beyond_old_timeout']=c.engine.process is state['process'] and c.engine.process.poll() is None
   checks['paused_session_does_not_export_frames']=c.engine.sent_id==state['sent']
   cmds.currentTime(4);cmds.setAttr(state['cube']+'.translateX',1)
   native_command(c.panel,True);state['phase']=2
  elif phase==2:
   if not ready():return
   same_scene('return_from_vp2')
   checks['selecting_active_eevee_is_idempotent']=ui.attach(c.panel) is c and viewport.register().has_image
   checks['edits_while_paused_reach_eevee']=c.engine.last_response.get('maya_frame')==4
   native_command(c.panel,False);state.update(phase=3,paused_at=time.monotonic())
  elif phase==3:
   if not c.parked or time.monotonic()-state['paused_at']<.15:return
   native_command(c.panel,True);state['phase']=4
  elif phase==4:
   if not ready():return
   state['cycles']+=1;same_scene('toggle_'+str(state['cycles']))
   if state['cycles']<6:
    native_command(c.panel,False);state.update(phase=3,paused_at=time.monotonic());return
   # Park with a real GPU request outstanding, before Maya imports its resized
   # shared texture. Returning must discard that camera without losing its ACK.
   from eevee_maya import native_controls
   c.timer.stop()
   data=c.snapshot(cmds.modelPanel(c.panel,query=True,camera=True),1920,1080,native_controls.read(c.panel))
   data['samples']=64;c.engine.submit(data,force=True)
   state['queued_token']=c.engine.sent_id
   native_command(c.panel,False);c.tick()
   state.update(phase=9,paused_at=time.monotonic());return
  elif phase==9:
   if not c.parked or time.monotonic()-state['paused_at']<.4:return
   checks['queued_frame_can_pause']=c.engine.sent_id==state['queued_token']
   native_command(c.panel,True);state['phase']=10
  elif phase==10:
   if not ready():return
   same_scene('pending_gpu_response')
   checks['old_camera_response_is_replaced']=c.engine.received_id>state['queued_token']
   window,panel=new_panel();state.update(window=window,new_panel=panel)
   checks['explicit_panel_transfer_reuses_controller']=ui.attach(panel) is c
   state['phase']=5
  elif phase==5:
   if not ready():return
   same_scene('other_panel')
   checks['only_destination_uses_eevee']=cmds.modelEditor('modelPanel4',query=True,rendererOverrideName=True)==''
   checks['camera_callback_follows_new_panel']=c.viewport_camera['path'].endswith(state['camera_shape'])
   cmds.deleteUI(state['window']);state.update(phase=6,paused_at=time.monotonic())
  elif phase==6:
   if not c.parked or time.monotonic()-state['paused_at']<4.2:return
   checks['closed_panel_keeps_scene_in_memory']=c.scene_stream is state['stream'] and c.engine.process is state['process']
   window,panel=new_panel();state.update(window=window,new_panel=panel)
   # Exercise native deferred attachment instead of the Python helper.
   cmds.modelEditor(panel,edit=True,rendererName='vp2Renderer',rendererOverrideName=viewport.NAME)
   omui.M3dView.getM3dViewFromModelPanel(panel).refresh(False,True)
   state['phase']=7
  elif phase==7:
   if not ready() or c.panel!=state['new_panel']:return
   same_scene('replacement_panel')
   # Capture immediately after reassignment, before a deferred draw can bind.
   cmds.modelEditor(c.panel,edit=True,rendererOverrideName='');c.tick()
   checks['capture_starts_from_parked_controller']=c.parked
   cmds.modelEditor(c.panel,edit=True,rendererOverrideName=viewport.NAME)
   cmds.playblast(format='image',compression='png',startTime=1,endTime=4,filename=str(OUT/'resumed_capture'),
    viewer=False,forceOverwrite=True,percent=100,widthHeight=(960,540),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
   checks['resumed_playblast_exact_frames']=not c.capture_error and [r['maya_frame'] for r in c.capture_records]==[1,2,3,4]
   checks['resumed_playblast_full_dimensions']=all((r['width'],r['height'])==(960,540) for r in c.capture_records)
   images=sorted(OUT.glob('resumed_capture.*.png'))
   checks['resumed_playblast_has_four_images']=len(images)==4
   checks['resumed_playblast_poses_differ']=len({hashlib.sha256(p.read_bytes()).hexdigest() for p in images})>1
   checks['resumed_playblast_deformations']=any(r['deformed_meshes'] for r in c.capture_records)
   state['phase']=8
  elif phase==8:
   if not ready():return
   same_scene('after_capture')
   reports['requests']=c.engine.sent_id;reports['scene_rebuilds']=c.engine.last_response['scene_rebuilds']
   reports['worker_pid']=c.engine.process.pid;old=c.engine.process;old_stream=c.scene_stream
   ui.stop()
   checks['explicit_stop_ends_worker']=old.poll() is not None and ui._controller is None
   checks['explicit_stop_releases_stream_and_gpu']=c.scene_stream is None and not viewport.register().gpu_image.receivers
   # Fresh startup must still be cancellable before its first image.
   fresh=ui.attach(state['new_panel']);process=fresh.engine.process
   cmds.modelEditor(fresh.panel,edit=True,rendererOverrideName='');fresh.tick()
   checks['cold_start_can_be_cancelled']=ui._controller is None and process.poll() is not None
   import maya.api.OpenMayaRender as render
   fresh=ui.attach(state['new_panel']);process=fresh.engine.process
   render.MRenderer.deregisterOverride(viewport._override)
   ui.stop()
   checks['shutdown_does_not_reregister_removed_renderer']=render.MRenderer.findRenderOverride(viewport.NAME) is None
   checks['removed_renderer_does_not_leave_worker']=process.poll() is not None
   finish()
 except Exception:finish(traceback.format_exc())

def start():
 global timer
 try:
  cmds.file(new=True,force=True)
  cube=cmds.polyCube()[0];target=cmds.duplicate(cube)[0]
  cmds.move(0,1.5,0,target+'.vtx[*]',relative=True,objectSpace=True)
  blend=cmds.blendShape(target,cube)[0];cmds.hide(target)
  cmds.setKeyframe(blend+'.weight[0]',time=1,value=0);cmds.setKeyframe(blend+'.weight[0]',time=4,value=1)
  mat=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(mat+'.color',0,0,0,type='double3');cmds.setAttr(mat+'.incandescence',.15,.45,.8,type='double3')
  sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(cube,edit=True,forceElement=sg)
  cmds.setAttr('persp.translate',0,0,14,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',8)
  camera,cam_shape=cmds.camera(orthographic=True,orthographicWidth=10)
  cmds.setAttr(camera+'.translate',0,1,14,type='double3')
  cmds.modelPanel('modelPanel4',edit=True,camera='persp')
  cmds.modelEditor('modelPanel4',edit=True,displayAppearance='smoothShaded',displayLights='all',grid=False,selectionHiliteDisplay=False)
  cmds.currentTime(1);cmds.select(clear=True);viewport.register();ui.install_menu()
  ui.runtime_settings().update(max_width=960,adaptive_quality=False)
  state.update(cube=cube,camera=camera,camera_shape=cam_shape)
  native_command('modelPanel4',True);omui.M3dView.getM3dViewFromModelPanel('modelPanel4').refresh(False,True)
  timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(100)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
