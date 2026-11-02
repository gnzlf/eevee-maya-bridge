"""Depth of field on a strongly rim-lit sphere: the blur must be smooth, not broken into strokes.

Owned profile only. Captures the out-of-focus sphere (foreground and background
cases) and measures stroke energy: high-frequency residue inside the blurred rim.
"""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore,QtGui
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport
PANEL='modelPanel4';W,H=960,540
S={'deadline':time.monotonic()+420};checks={};reports={};timer=None

def capture(label):
 c=S['c']
 cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(OUT/label),viewer=False,forceOverwrite=True,
  percent=100,widthHeight=(W,H),showOrnaments=False,offScreen=True,editorPanelName=PANEL)
 image=QtGui.QImage(str(next(OUT.glob(label+'.*.png')))).convertToFormat(QtGui.QImage.Format_RGB32)
 w,h=image.width(),image.height()
 lum=[[0]*w for _ in range(h)]
 for y in range(h):
  for x in range(w):
   c_=image.pixel(x,y);lum[y][x]=((c_>>16)&255)*.2126+((c_>>8)&255)*.7152+(c_&255)*.0722
 # Stroke energy: mean |laplacian| over the region around the sphere. A smooth
 # blur has a small second derivative; dotted/streaked copies of the rim do not.
 x0,x1,y0,y1=int(w*.25),int(w*.75),int(h*.1),int(h*.9);total=0;n=0;peak=0
 for y in range(y0,y1):
  for x in range(x0,x1):
   l=abs(4*lum[y][x]-lum[y-1][x]-lum[y+1][x]-lum[y][x-1]-lum[y][x+1]);total+=l;n+=1;peak=max(peak,lum[y][x])
 reports[label]={'transport':c.engine.last_response.get('transport'),'stroke_energy':round(total/n,3),'peak':round(peak,1),'center':round(lum[h//2][w//2],1),
  'dof':(c.engine.last_response.get('camera') or {}).get('dof')}
 return reports[label]

def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'reports':reports,'error':error},indent=2,default=str))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def tests():
 cam='perspShape'
 cmds.setAttr(cam+'.depthOfField',False);sharp=capture('sharp')
 cmds.setAttr(cam+'.depthOfField',True)
 cmds.setAttr(cam+'.focusDistance',2000);cmds.setAttr(cam+'.fStop',float(os.environ.get('EEVEE_DOF_FSTOP',1.4)));back=capture('blur_focus_behind')
 cmds.setAttr(cam+'.focusDistance',140);front=capture('blur_focus_in_front')
 cmds.setAttr(cam+'.focusDistance',275);focused=capture('focused')
 checks['dof_active']=bool(back['dof'])
 # Strokes add high-frequency energy; a real blur removes it and spreads the rim.
 checks['blur_smooth_focus_behind']=back['stroke_energy']<sharp['stroke_energy']*.9
 checks['blur_smooth_focus_in_front']=front['stroke_energy']<sharp['stroke_energy']*.9
 checks['rim_spread_focus_behind']=back['peak']<sharp['peak']*.6
 checks['rim_spread_focus_in_front']=front['peak']<sharp['peak']*.6
 checks['focused_stays_sharp']=focused['peak']>sharp['peak']*.9
 # Presentation cost: Maya redraws reuse the last Eevee frame, so this times the DOF pass.
 def redraw_ms(count=40):
  for _ in range(5):cmds.refresh(force=True)
  t0=time.perf_counter()
  for _ in range(count):cmds.refresh(force=True)
  return round((time.perf_counter()-t0)*1000/count,2)
 cmds.setAttr(cam+'.focusDistance',140);reports['redraw_ms_dof_max_blur']=redraw_ms()
 cmds.setAttr(cam+'.depthOfField',False);reports['redraw_ms_no_dof']=redraw_ms()

def tick():
 try:
  c=S['c']
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:3000])
  if not c.presented_once or c.force or not c.engine.available:return
  timer.stop();tests();finish()
 except Exception:finish(traceback.format_exc())

def modal_guard():
 from PySide2 import QtWidgets
 def modal():
  w=QtWidgets.QApplication.activeModalWidget()
  if w:
   labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
   b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','') in ('Allow','Allow All')),None)
   if b and 'eeveeBridge' in ' '.join(labels):b.click()
 t=QtCore.QTimer();t.timeout.connect(modal);t.start(300);S['modal']=t

def start():
 global timer
 try:
  modal_guard()
  cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True)
  cmds.file(new=True,force=True)
  sphere=cmds.polySphere(radius=30,subdivisionsX=64,subdivisionsY=48)[0]
  mat=cmds.shadingNode('blinn',asShader=True);sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True)
  cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(sphere,edit=True,forceElement=sg)
  cmds.setAttr(mat+'.color',.35,.35,.35,type='double3')
  # Rim: strong spot from behind and slightly above, plus a dim key from the front.
  rim=cmds.spotLight(intensity=float(os.environ.get('EEVEE_DOF_RIM',40)),coneAngle=50)
  t=cmds.listRelatives(rim,parent=True)[0];cmds.setAttr(t+'.translate',0,60,-160,type='double3')
  cmds.setAttr(t+'.rotate',*cmds.angleBetween(euler=True,v1=(0,0,-1),v2=(0,-60,160)),type='double3')
  key=cmds.directionalLight(intensity=.15);kt=cmds.listRelatives(key,parent=True)[0];cmds.setAttr(kt+'.rotate',-20,20,0,type='double3')
  cmds.setAttr('persp.translate',0,0,300,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  cmds.setAttr('perspShape.focalLength',85);cmds.setAttr('perspShape.farClipPlane',10000);cmds.setAttr('perspShape.nearClipPlane',1)
  cmds.modelPanel(PANEL,edit=True,camera='persp')
  cmds.modelEditor(PANEL,edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,
   manipulators=False,selectionHiliteDisplay=False,depthOfFieldPreview=True)
  cmds.setAttr('hardwareRenderingGlobals.renderDepthOfField',True)
  if os.environ.get('EEVEE_DOF_CPU'):
   # Exercise the shared-memory fallback (EeveeBlit.ogsfx) instead of the GPU bridge.
   original=ui.runtime_settings;ui.runtime_settings=lambda *a,**k:dict(original(*a,**k),gpu_transport=False)
  cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach(PANEL);c.engine.config.update(max_width=W,adaptive_quality=False)
  S['c']=c;timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
