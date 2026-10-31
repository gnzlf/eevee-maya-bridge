"""Measure settled edit latency and worker render cost in an owned Maya profile.

Latency waits for presentation with no outstanding request. It includes native
UI refresh and idle-quality recovery; it is not first-preview or scanout latency.
"""
import hashlib,json,os,statistics,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
import maya.api.OpenMayaUI as omui
import maya.OpenMayaUI as qtui
from PySide2 import QtCore,QtWidgets
from shiboken2 import wrapInstance
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
PANEL='eeveeInteractionModelPanel' if os.environ.get('EEVEE_EXACT_ASPECT')=='1' else 'modelPanel4'
from eevee_maya import ui,viewport,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
state={'deadline':time.monotonic()+600,'phase':-1,'sample':0,'rows':[]};timer=None;checks={};reports={}
phases=[(False,'object'),(False,'light_move'),(False,'light_intensity'),(True,'object'),(True,'light_move'),(True,'light_intensity')]
def finish(error=None):
 if timer:timer.stop()
 checks['source_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
 for adaptive,kind in phases:
  rows=[r for r in state['rows'] if r['adaptive']==adaptive and r['kind']==kind]
  if rows:reports[str(adaptive)+'_'+kind]={'samples':len(rows),'median_latency_ms':statistics.median(r['latency_ms'] for r in rows),'median_export_ms':statistics.median(r['export_ms'] for r in rows),'median_render_ms':statistics.median(r['render_ms'] for r in rows),'widths':sorted(set(r['width'] for r in rows)),'rebuilds':sorted(set(r['rebuilds'] for r in rows)),'median_sync_ms':statistics.median(r['worker'].get('sync',0) for r in rows),'median_draw_ms':statistics.median(r['worker'].get('draw_color',0) for r in rows)}
 (OUT/'result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'version':__version__,'checks':checks,'reports':reports,'rows':state['rows'],'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(100,lambda:cmds.quit(force=True))
def edit():
 c=state['c'];adaptive,kind=phases[state['phase']];i=state['sample'];state.update(start=time.perf_counter(),wait=c.engine.sent_id)
 if kind=='object':cmds.setAttr(state['object']+'.translateX',state['object_x']+(.1 if i%2 else -.1))
 elif kind=='light_move':cmds.setAttr(state['light_parent']+'.rotateY',-25+(i%2)*12)
 else:cmds.setAttr(state['light']+'.intensity',1+(i%2)*.3)
 state['view'].refresh(False,True)
def next_phase():
 c=state['c'];state['phase']+=1;state['sample']=0
 if state['phase']==len(phases):
  checks['all_edits_presented']=len(state['rows'])==len(phases)*8
  checks['gpu_error_free']=viewport._override.gpu_image.error is None
  c.engine.config['adaptive_quality']=True;c.force=True;state['settle']=time.monotonic();state['ending']=True;return
 c.engine.config['adaptive_quality']=phases[state['phase']][0];c.force=True
 # Start each comparison from a settled full-resolution frame.
 state['settle']=time.monotonic();state['warm_phase']=True
def tick():
 try:
  c=state['c'];view=state['view']
  if time.monotonic()-state.get('heartbeat',0)>1:
   state['heartbeat']=time.monotonic()
   (OUT/'progress.json').write_text(json.dumps({'phase':state['phase'],'sample':state['sample'],'sent':c.engine.sent_id,'received':c.engine.received_id,'presented':viewport._override.gpu_image.displayed_id,'force':c.force,'size':[view.portWidth(),view.portHeight()]}))
  if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response))
  view.refresh(False,True)
  if not c.presented_once or not c.engine.available or c.force or viewport._override.gpu_image.displayed_id!=c.engine.received_id:return
  if state.get('ending'):
   if time.monotonic()-state['settle']<1 or c.engine.last_response['width']!=1920:return
   checks['restores_1920_when_idle']=True
   cmds.playblast(format='image',compression='png',startTime=cmds.currentTime(query=True),endTime=cmds.currentTime(query=True),filename=str(OUT/'fullhd'),viewer=False,forceOverwrite=True,percent=100,widthHeight=(1920,1080),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
   checks['fullhd_capture_valid']=bool(c.capture_records) and not c.capture_error and all((r['width'],r['height'])==(1920,1080) for r in c.capture_records)
   if 'gpu_resource_reuses' in c.engine.last_response:
    checks['gpu_buffers_reused']=c.engine.last_response['gpu_resource_reuses']>0
    checks['object_edits_use_adaptive_width']=all(r['width']<=960 for r in state['rows'] if r['adaptive'] and r['kind']=='object')
    checks['full_resolution_editing_preserved']=all(r['width']==1920 for r in state['rows'] if not r['adaptive'])
   finish();return
  if state['phase']==-1:next_phase();return
  if state.get('warm_phase'):
   if time.monotonic()-state['settle']<.8 or c.engine.last_response['width']!=1920:return
   state['warm_phase']=False;edit();return
  if c.engine.received_id<=state['wait']:return
  r=c.engine.last_response;adaptive,kind=phases[state['phase']]
  state['rows'].append({'adaptive':adaptive,'kind':kind,'sample':state['sample'],'latency_ms':(time.perf_counter()-state['start'])*1000,'export_ms':c.timings.get('export_ms',0),'render_ms':r['seconds']*1000,'worker':r.get('timings_ms',{}),'width':r['width'],'height':r['height'],'rebuilds':r.get('scene_rebuilds'),'interactive':r.get('interactive'),'retired_gpu_pools':r.get('retired_gpu_pools')})
  state['rows'][-1].update(resource_allocations=r.get('gpu_resource_allocations'),resource_reuses=r.get('gpu_resource_reuses'))
  state['sample']+=1
  if state['sample']==8:next_phase()
  else:edit()
 except Exception:finish(traceback.format_exc())
def start():
 global timer
 def modal():
  w=QtWidgets.QApplication.activeModalWidget()
  if w:
   labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
   (OUT/'modal.json').write_text(json.dumps({'title':w.windowTitle(),'labels':labels}))
   if w.windowTitle()=='Untrusted Plugin Loading - Security Warning' and any('<b>eeveeBridge.py</b>' in t and (BRIDGE/'plug-ins').as_posix() in t for t in labels):
    b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','')=='Allow'),None)
    if b:b.click()
 observer=QtCore.QTimer();observer.timeout.connect(modal);observer.start(500);state['observer']=observer
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True);cmds.loadPlugin('mtoa',quiet=True)
 cmds.file(SOURCE.as_posix(),open=True,force=True,prompt=False,executeScriptNodes=False);observer.stop();ui.stop()
 mel.eval('setNamedPanelLayout "Single Perspective View"')
 if os.environ.get('EEVEE_EXACT_ASPECT')=='1':
  # Use an independent layout; fixing the child of Maya's main layout can
  # create a resize/paint feedback loop in Qt.
  cmds.modelEditor('modelPanel4',edit=True,allObjects=False,grid=False)
  window=cmds.window('eeveeInteractionTestWindow',widthHeight=(1280,800))
  cmds.paneLayout(configuration='single');cmds.modelPanel(PANEL,menuBarVisible=False)
  cmds.showWindow(window)
 cameras=[n for n in cmds.ls(type='camera',long=True) if not cmds.camera(n,query=True,startupCamera=True)]
 cmds.modelPanel(PANEL,edit=True,camera=cameras[0] if cameras else 'persp')
 cmds.modelEditor(PANEL,edit=True,displayLights='all',displayAppearance='smoothShaded',displayTextures=True,grid=False,shadows=True,selectionHiliteDisplay=False)
 if os.environ.get('EEVEE_EXACT_ASPECT')=='1':
  view=omui.M3dView.getM3dViewFromModelPanel(PANEL)
  widget=wrapInstance(int(qtui.MQtUtil.findWindow(window)),QtWidgets.QWidget)
  for _ in range(2):
   QtWidgets.QApplication.processEvents()
   widget.resize(widget.width()+1280-view.portWidth(),widget.height()+720-view.portHeight())
  QtWidgets.QApplication.processEvents();cmds.setFocus(PANEL)
 meshes=[m for m in cmds.ls(type='mesh',long=True) if not cmds.getAttr(m+'.intermediateObject')]
 parents=[cmds.listRelatives(m,parent=True,fullPath=True)[0] for m in meshes]
 obj=next((n for n in parents if cmds.getAttr(n+'.translateX',settable=True)),None)
 if obj is None:obj=cmds.polySphere()[0]
 light=cmds.spotLight(intensity=1);parent=cmds.listRelatives(light,parent=True,fullPath=True)[0]
 cmds.setAttr(parent+'.translate',0,10,10,type='double3');cmds.setAttr(parent+'.rotateX',-45)
 cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach(PANEL);c.engine.config.update(max_width=1920,adaptive_quality=False)
 state.update(c=c,view=omui.M3dView.getM3dViewFromModelPanel(c.panel),object=obj,object_x=cmds.getAttr(obj+'.translateX'),light=light,light_parent=parent)
 timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(16)
def safe():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
