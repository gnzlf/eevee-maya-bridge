"""Resizing the Eevee panel (maximize with space / layout change) must not leave a stretched image.

Owned profile only. A sphere in the centre of the frame must stay round after the
panel grows or shrinks; the presented render must match the panel aspect.
"""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.utils
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore,QtGui
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport
PANEL='modelPanel4'
S={'deadline':time.monotonic()+420,'steps':[]};checks={};reports={};timer=None

def capture(label):
 c=S['c'];view=omui.M3dView.getM3dViewFromModelPanel(PANEL)
 view.refresh(False,True)
 im=om.MImage();view.readColorBuffer(im,True);path=OUT/(label+'.png');im.writeToFile(str(path),'png')
 image=QtGui.QImage(str(path)).convertToFormat(QtGui.QImage.Format_RGB32);w,h=image.width(),image.height()
 # Bright sphere on a dark background: bounding box of bright pixels.
 xs=[];ys=[]
 for y in range(0,h,2):
  for x in range(0,w,2):
   p=image.pixel(x,y)
   if ((p>>16)&255)+((p>>8)&255)+(p&255)>240:xs.append(x);ys.append(y)
 bw=(max(xs)-min(xs)+2) if xs else 0;bh=(max(ys)-min(ys)+2) if ys else 0
 r=c.engine.last_response;frame=viewport.register().gpu_image.frame or {}
 rw,rh=r.get('width') or 1,r.get('height') or 1
 reports[label]={'panel':[view.portWidth(),view.portHeight()],'image':[w,h],'render':[rw,rh],
  'panel_aspect':round(view.portWidth()/max(1,view.portHeight()),3),'render_aspect':round(rw/rh,3),
  'sphere_box':[bw,bh],'sphere_ratio':round(bw/max(1,bh),3),'received':c.engine.received_id,'sent':c.engine.sent_id,
  'transport':r.get('transport')}
 return reports[label]

def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'passed':not error and bool(checks) and all(checks.values()),'checks':checks,'reports':reports,'error':error},indent=2,default=str))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def settle(seconds=2.5):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents,50)

def layout(name):
 mel.eval('setNamedPanelLayout "%s"'%name)
 # Keep the Eevee panel in the persp slot of whatever layout Maya builds.
 settle(.3)

def pop():
 # Same effect on the Eevee panel as tapping space: it grows to a much wider shape, and back.
 S['wide']=not S.get('wide');S['main'].resize(*((2600,1000) if S['wide'] else (1100,1300)))

def frozen(fn):
 # A heavy scene keeps showing the previous frame while Eevee renders the new
 # size. Freeze the controller to observe exactly that presented stale frame.
 c=S['c'];c.timer.stop();c.tick=lambda *a,**k:None;sent=c.engine.sent_id
 try:
  fn();settle(1.5);r=capture('stale_'+fn.__name__+str(S['wide']));r['frozen']=c.engine.sent_id==sent;return r
 finally:
  del c.tick;c.timer.start(int(c.engine.config['interval_ms']));c.force=True

def tests():
 small=capture('split');settle(.5)
 stale_big=frozen(pop);settle();big=capture('maximized_settled')
 stale_small=frozen(pop);settle();back=capture('restored_settled')
 for label,r in (('split',small),('maximized',big),('restored',back)):
  checks[label+'_render_matches_panel']=abs(r['render_aspect']-r['panel_aspect'])<.03
  checks[label+'_sphere_round']=abs(r['sphere_ratio']-1)<.08
 checks['panel_actually_resized']=abs(big['panel_aspect']-small['panel_aspect'])>.5
 checks['stale_frame_round_after_maximize']=stale_big['frozen'] and abs(stale_big['sphere_ratio']-1)<.08
 checks['stale_frame_round_after_restore']=stale_small['frozen'] and abs(stale_small['sphere_ratio']-1)<.08

def tick():
 try:
  c=S['c']
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:3000])
  if not c.presented_once or c.force or not c.engine.available:return
  timer.stop();settle(1);tests();finish()
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
  sphere=cmds.polySphere(radius=3,subdivisionsX=48,subdivisionsY=32)[0]
  mat=cmds.shadingNode('lambert',asShader=True);sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True)
  cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(sphere,edit=True,forceElement=sg)
  cmds.setAttr(mat+'.color',1,1,1,type='double3');cmds.setAttr(mat+'.incandescence',.8,.8,.8,type='double3')
  cmds.setAttr('persp.translate',0,0,30,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
  # Main window near square so side-by-side panes are tall and maximizing changes the aspect a lot.
  from PySide2 import QtWidgets
  main=next(w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName()=='MayaWindow')
  main.showNormal();main.resize(1100,1300);S['main']=main;settle(.5)
  layout('Single Perspective View');settle(.5)
  reports['layout']={p_:[omui.M3dView.getM3dViewFromModelPanel(p_).portWidth(),omui.M3dView.getM3dViewFromModelPanel(p_).portHeight()] for p_ in cmds.getPanel(visiblePanels=True) or [] if cmds.getPanel(typeOf=p_)=='modelPanel'}
  panels=cmds.getPanel(visiblePanels=True) or []
  if PANEL not in panels:raise RuntimeError('modelPanel4 no visible en Two Panes: %s'%panels)
  cmds.modelPanel(PANEL,edit=True,camera='persp')
  cmds.modelEditor(PANEL,edit=True,grid=False,displayAppearance='smoothShaded',manipulators=False,selectionHiliteDisplay=False,headsUpDisplay=False)
  if os.environ.get('EEVEE_RESIZE_CPU'):
   # Exercise the shared-memory fallback (EeveeBlit.ogsfx) instead of the GPU bridge.
   original=ui.runtime_settings;ui.runtime_settings=lambda *a,**k:dict(original(*a,**k),gpu_transport=False)
  cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach(PANEL)
  S['c']=c;timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
