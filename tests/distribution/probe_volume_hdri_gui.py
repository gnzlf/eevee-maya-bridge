"""Volumetric fog with an HDRI dome: beams must stay readable; the HDRI may light the fog only on request.

Owned profile only. Also screenshots the loading HUD while Eevee starts.
"""
import json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore,QtGui
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['EEVEE_INTERACTION_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUT/'interaction_regression_profile':raise RuntimeError('Owned profile required')
BRIDGE=Path(os.environ.get('EEVEE_INSTALLED_ROOT',ROOT));sys.path.insert(0,str(BRIDGE/'scripts'))
from eevee_maya import ui,viewport
PANEL='modelPanel4';W,H=960,540
HDRI=os.environ.get('EEVEE_VOLUME_HDRI',str(ROOT/'diagnostics/calibration.hdr'))
S={'deadline':time.monotonic()+420,'loading':0,'labels':[]};checks={};reports={};timer=None
POINTS={'beam':(480,200),'beside':(150,200),'floor':(480,470)}

def capture(label):
 c=S['c']
 cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(OUT/label),viewer=False,forceOverwrite=True,
  percent=100,widthHeight=(W,H),showOrnaments=False,offScreen=True,editorPanelName=PANEL)
 image=QtGui.QImage(str(next(OUT.glob(label+'.*.png'))))
 def lum(x,y):
  p=[image.pixelColor(x+i,y+j) for i in range(-4,5) for j in range(-4,5)]
  return sum(q.red()+q.green()+q.blue() for q in p)/(3*len(p))
 values={k:round(lum(*xy),1) for k,xy in POINTS.items()}
 st=c.engine.last_response.get('eevee_state') or {}
 reports[label]=dict(values,clamp=st.get('volume_indirect_clamp'),environment=st.get('environment',{}).get('sources'))
 return values

def finish(error=None):
 if timer:timer.stop()
 (OUT/'result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'reports':reports,
  'loading_labels':S['labels'],'error':error},indent=2,default=str))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def tests():
 node=ui.scene_settings(select=False);dome=S['dome']
 cmds.setAttr(dome+'.visibility',False);nodome=capture('no_hdri')
 cmds.setAttr(dome+'.visibility',True);hdri=capture('hdri_default')
 cmds.setAttr(node+'.fogWorldLight',True);lit=capture('hdri_lights_fog')
 cmds.setAttr(node+'.fogWorldLight',False);back=capture('hdri_default_again')
 cmds.setAttr(node+'.volumetrics',False);nofog=capture('hdri_no_fog')
 contrast=lambda v:v['beam']-v['beside']
 checks['beam_visible_without_hdri']=contrast(nodome)>8
 checks['beam_visible_with_hdri']=contrast(hdri)>max(8,contrast(nodome)*.5)
 checks['hdri_lights_scene']=hdri['floor']>nodome['floor']+5
 checks['option_hdri_lights_fog']=lit['beside']>hdri['beside']+5
 checks['option_restores']=abs(back['beside']-hdri['beside'])<3
 checks['fog_visible_over_hdri']=hdri['beam']>nofog['beam']+5
 checks['clamp_only_with_fog']=(reports['hdri_default']['clamp'] or 0)>0 and reports['hdri_lights_fog']['clamp']==0 and reports['hdri_no_fog']['clamp']==0

def tick():
 try:
  c=S['c']
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:3000])
  if not c.presented_once:
   if time.monotonic()-S.get('lt',0)>.6 and S['loading']<12:
    S['lt']=time.monotonic();view=omui.M3dView.getM3dViewFromModelPanel(PANEL)
    im=om.MImage();view.readColorBuffer(im,True);im.writeToFile(str(OUT/('loading%d.png'%S['loading'])),'png');S['loading']+=1
    S['labels'].append(viewport.register().loading.last_status.get('label'))
   return
  if c.force or not c.engine.available:return
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
  cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True);cmds.loadPlugin('mtoa',quiet=True)
  cmds.file(new=True,force=True)
  cmds.polyPlane(width=40,height=40)
  spot=cmds.spotLight(intensity=float(os.environ.get('EEVEE_VOLUME_SPOT',3)),coneAngle=40)
  t=cmds.listRelatives(spot,parent=True)[0];cmds.setAttr(t+'.translateY',8);cmds.setAttr(t+'.rotateX',-90)
  dome=cmds.shadingNode('aiSkyDomeLight',asLight=True);S['dome']=dome;shape=cmds.listRelatives(dome,shapes=True)[0]
  f=cmds.shadingNode('file',asTexture=True,isColorManaged=True);cmds.setAttr(f+'.fileTextureName',HDRI,type='string')
  cmds.connectAttr(f+'.outColor',shape+'.color',force=True)
  node=ui.scene_settings(select=False)
  for key,value in (('volumetrics',True),('density',float(os.environ.get('EEVEE_VOLUME_DENSITY',.15))),('fogAutoRange',False),('fogDistance',40),('anisotropy',0)):
   cmds.setAttr(node+'.'+key,value)
  cmds.setAttr(node+'.fogColor',1,1,1,type='double3')
  cmds.setAttr('persp.translate',0,3,15,type='double3');cmds.setAttr('persp.rotate',-5,0,0,type='double3')
  cmds.setAttr('perspShape.farClipPlane',1000)
  cmds.modelPanel(PANEL,edit=True,camera='persp')
  cmds.modelEditor(PANEL,edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,manipulators=False,selectionHiliteDisplay=False)
  cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach(PANEL);c.engine.config.update(max_width=W,adaptive_quality=False)
  S['c']=c;timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
 except Exception:finish(traceback.format_exc())

maya.utils.executeDeferred(start)
