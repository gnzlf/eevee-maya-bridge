"""Measure image-based specular in Viewport 2.0 vs Eevee under a uniform white SkyDome.

Colour management is disabled so pixels are linear. Each sphere samples the
centre (normal incidence) and a point near the rim (grazing).
"""
import json,os,sys,time,traceback
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
from eevee_maya import ui,viewport
PANEL='eeveeIblPanel';W,H=1280,720
S={'deadline':time.monotonic()+300};timers={}
MATS=[
 ('ss_ior15_r0','standardSurface',dict(base=0,specular=1,specularRoughness=0,specularIOR=1.5)),
 ('ss_ior21_r0','standardSurface',dict(base=0,specular=1,specularRoughness=0,specularIOR=2.1)),
 ('ss_ior15_r03','standardSurface',dict(base=0,specular=1,specularRoughness=.3,specularIOR=1.5)),
 ('ss_diffuse','standardSurface',dict(base=1,specular=0,baseColor=(1,1,1))),
 ('blinn_s05_e03','blinn',dict(color=(0,0,0),diffuse=0,specularColor=(.5,.5,.5),eccentricity=.3,reflectivity=.5)),
 ('blinn_s1_e03_r0','blinn',dict(color=(0,0,0),diffuse=0,specularColor=(1,1,1),eccentricity=.3,reflectivity=0)),
 ('blinn_s05_e01','blinn',dict(color=(0,0,0),diffuse=0,specularColor=(.5,.5,.5),eccentricity=.1,reflectivity=.5)),
 ('lambert_white','lambert',dict(color=(1,1,1),diffuse=1)),
]

def sample(path):
 im=om.MImage();im.readFromFile(str(path));w,h=im.getSize();px=im.pixels()
 def at(x,y):
  i=((h-1-y)*w+x)*4 if False else (y*w+x)*4
  return [px[i]/255.0,px[i+1]/255.0,px[i+2]/255.0]
 out={}
 for name,(cx,cy,r) in S['spots'].items():
  out[name]={'center':at(cx,cy),'rim':at(cx+int(r*.92),cy)}
 return out

def grab(name):
 view=omui.M3dView.getM3dViewFromModelPanel(PANEL);view.refresh(False,True)
 im=om.MImage();view.readColorBuffer(im,True);path=OUT/(name+'.png');im.writeToFile(str(path),'png')
 # Screen grab of the GL widget as well: what the user actually sees.
 w=wrapInstance(int(view.widget()),QtWidgets.QWidget);QtWidgets.QApplication.processEvents()
 screen=QtWidgets.QApplication.primaryScreen().grabWindow(w.winId());screen.save(str(OUT/(name+'_screen.png')))
 return path

def finish(error=None):
 for t in timers.values():t.stop()
 res={'error':error}
 try:
  res['spots']=S.get('spots');c=S.get('c')
  if c:res['status']=c.engine.status;res['renderer']=cmds.modelEditor(PANEL,query=True,rendererOverrideName=True);res['gpu_error']=viewport.register().gpu_image.error
 except Exception:res['sample_error']=traceback.format_exc()
 (OUT/'result.json').write_text(json.dumps(res,indent=2,default=str))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def log(m):
 with open(OUT/'probe.log','a',encoding='utf-8') as f:f.write('%.3f %s\n'%(time.monotonic(),m))

def tick():
 try:
  c=S['c']
  if time.monotonic()-S.get('hb',0)>.5:
   S['hb']=time.monotonic();log('renderer=%r parked=%s status=%s sent=%s recv=%s disp=%s pres=%s'%(cmds.modelEditor(PANEL,query=True,rendererOverrideName=True),c.parked,c.engine.status,c.engine.sent_id,c.engine.received_id,viewport.register().gpu_image.displayed_id,c.presented_once))
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:3000])
  if (c.force or not c.presented_once or c.engine.sent_id!=c.engine.received_id or c.engine.last_response.get('interactive')
      or viewport.register().gpu_image.displayed_id!=c.engine.received_id):S['since']=time.monotonic();return
  if time.monotonic()-S['since']<3:return
  grab('eevee');(OUT/'eevee_state.json').write_text(json.dumps(c.engine.last_response.get('eevee_state'),indent=2,default=str));finish()
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
 log('setup start')
 modal_guard()
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True);cmds.loadPlugin('mtoa',quiet=True)
 cmds.file(new=True,force=True);cmds.colorManagementPrefs(edit=True,cmEnabled=True);cmds.colorManagementPrefs(edit=True,viewTransformName='Raw (sRGB)') if 'Raw (sRGB)' in (cmds.colorManagementPrefs(query=True,viewTransformNames=True) or []) else None
 dome=cmds.shadingNode('aiSkyDomeLight',asLight=True);shape=cmds.listRelatives(dome,shapes=True)[0]
 cmds.setAttr(shape+'.color',1,1,1,type='double3');cmds.setAttr(shape+'.intensity',1);cmds.setAttr(shape+'.camera',0)
 n=len(MATS);spacing=2.4
 for i,(name,kind,attrs) in enumerate(MATS):
  sphere=cmds.polySphere(name=name,subdivisionsX=64,subdivisionsY=48)[0];cmds.setAttr(sphere+'.translateX',(i-(n-1)/2)*spacing)
  mat=cmds.shadingNode(kind,asShader=True,name=name+'_mat');sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True,name=name+'SG')
  cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader')
  for a,v in attrs.items():
   if isinstance(v,tuple):cmds.setAttr(mat+'.'+a,*v,type='double3')
   else:cmds.setAttr(mat+'.'+a,v)
  cmds.sets(sphere,edit=True,forceElement=sg)
 cam,cs=cmds.camera(name='IblCam',focalLength=600,horizontalFilmAperture=36/25.4,filmFit=1)
 cmds.setAttr(cam+'.translateZ',600/36*(n*spacing+.4));cmds.setAttr(cs+'.farClipPlane',10000)
 win=cmds.window(widthHeight=(W,H+80));cmds.paneLayout(configuration='single');cmds.modelPanel(PANEL,menuBarVisible=False,camera=cam);cmds.showWindow(win)
 view=omui.M3dView.getM3dViewFromModelPanel(PANEL);widget=wrapInstance(int(qtui.MQtUtil.findWindow(win)),QtWidgets.QWidget)
 for _ in range(2):QtWidgets.QApplication.processEvents();widget.resize(widget.width()+W-view.portWidth(),widget.height()+H-view.portHeight())
 cmds.modelEditor(PANEL,edit=True,displayLights='all',displayAppearance='smoothShaded',grid=False,lights=False,cameras=False,headsUpDisplay=False,shadows=False,selectionHiliteDisplay=False)
 cmds.setAttr('hardwareRenderingGlobals.ssaoEnable',False);cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',True)
 cmds.select(clear=True)
 pw,ph=view.portWidth(),view.portHeight();width_world=n*spacing+.4;scale=pw/width_world
 S['spots']={name:(int(pw/2+(i-(n-1)/2)*spacing*scale),int(ph/2),int(scale)) for i,(name,_,_) in enumerate(MATS)}
 for _ in range(5):QtWidgets.QApplication.processEvents();cmds.refresh(force=True)
 grab('vp2')
 hdri=os.environ.get('EEVEE_IBL_HDRI')
 if hdri:
  f=cmds.shadingNode('file',asTexture=True,isColorManaged=True);cmds.setAttr(f+'.fileTextureName',hdri,type='string');cmds.setAttr(f+'.colorSpace','Raw',type='string')
  cmds.connectAttr(f+'.outColor',shape+'.color',force=True)
  for value in (1.0,.365):
   cmds.setAttr(shape+'.intensity',value)
   for _ in range(8):QtWidgets.QApplication.processEvents();cmds.refresh(force=True)
   grab('vp2_hdri_%s'%value)
  finish();return
 cmds.setFocus(PANEL);QtWidgets.QApplication.processEvents()
 viewport.register();c=ui.attach(PANEL);c.engine.config.update(max_width=W,adaptive_quality=False);S['c']=c;S['since']=time.monotonic()
 if c.panel!=PANEL:raise RuntimeError('attach chose '+c.panel)
 log('attached renderer=%r'%cmds.modelEditor(PANEL,query=True,rendererOverrideName=True))
 timers['t']=QtCore.QTimer();timers['t'].timeout.connect(tick);timers['t'].start(200)

def safe():
 try:setup()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
