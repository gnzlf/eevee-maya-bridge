"""Open the Eevee settings window in an owned profile and screenshot every tab."""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
import maya.OpenMayaUI as qtui
from PySide2 import QtCore,QtWidgets
from shiboken2 import wrapInstance
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport,settings_window
S={'checks':{},'deadline':time.monotonic()+240};timers={}

def finish(error=None):
 for t in timers.values():t.stop()
 (OUT/'result.json').write_text(json.dumps({'error':error,'checks':S['checks'],'passed':not error and all(S['checks'].values())},indent=2))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def shoot():
 try:
  w=settings_window._window;widget=wrapInstance(int(qtui.MQtUtil.findWindow(w.window)),QtWidgets.QWidget)
  labels=cmds.tabLayout(w.tabs,query=True,tabLabel=True);ids=cmds.tabLayout(w.tabs,query=True,childArray=True)
  S['checks']['five_tabs']=len(labels)==5;S['checks']['hdri_tab_label']=any('HDRI' in l for l in labels)
  tab=wrapInstance(int(qtui.MQtUtil.findControl(w.tabs)),QtWidgets.QWidget)
  S['checks']['tabs_fill_window']=tab.height()>widget.height()*.7
  for i,label in enumerate(labels):
   cmds.tabLayout(w.tabs,edit=True,selectTabIndex=i+1)
   for _ in range(3):QtWidgets.QApplication.processEvents()
   # expand collapsed sections for a second screenshot
   widget.grab().save(str(OUT/('tab%d_%s.png'%(i+1,label.split()[0]))))
   frames=[c for c in (cmds.lsUI(type='frameLayout') or []) if cmds.frameLayout(c,query=True,collapsable=True) and cmds.control(c,query=True,fullPathName=True).startswith(cmds.control(ids[i],query=True,fullPathName=True))]
   for f in frames:cmds.frameLayout(f,edit=True,collapse=False)
   for _ in range(3):QtWidgets.QApplication.processEvents()
   widget.grab().save(str(OUT/('tab%d_%s_open.png'%(i+1,label.split()[0]))))
  widget.resize(380,420)
  for _ in range(3):QtWidgets.QApplication.processEvents()
  cmds.tabLayout(w.tabs,edit=True,selectTabIndex=1);QtWidgets.QApplication.processEvents()
  widget.grab().save(str(OUT/'small_window.png'))
  S['checks']['tabs_follow_resize']=tab.height()>widget.height()*.6
  finish()
 except Exception:finish(traceback.format_exc())

def wait():
 try:
  c=S['c']
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if not c.presented_once:return
  timers['wait'].stop()
  # A selected light populates the light section.
  cmds.select(S['light'],replace=True)
  settings_window.show(c);QtCore.QTimer.singleShot(1500,shoot)
 except Exception:finish(traceback.format_exc())

def modal_guard():
 def modal():
  w=QtWidgets.QApplication.activeModalWidget()
  if w:
   labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
   (OUT/'modal.json').write_text(json.dumps({'title':w.windowTitle(),'labels':labels}))
   b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','') in ('Allow','Allow All')),None)
   if b and 'eeveeBridge' in ' '.join(labels):b.click()
 t=QtCore.QTimer();t.timeout.connect(modal);t.start(300);timers['modal']=t

def setup():
 modal_guard()
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True)
 try:cmds.loadPlugin('mtoa',quiet=True)
 except Exception:pass
 cmds.file(new=True,force=True);cmds.polySphere();S['light']=cmds.spotLight()
 try:
  import maya.mel as mel;mel.eval('setNamedPanelLayout "Single Perspective View"')
 except Exception:pass
 viewport.register();ui.install_menu();c=ui.attach('modelPanel4');S['c']=c
 timers['wait']=QtCore.QTimer();timers['wait'].timeout.connect(wait);timers['wait'].start(200)

def safe():
 try:setup()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
