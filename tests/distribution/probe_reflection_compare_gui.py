"""Compare Viewport 2.0 and Eevee reflections on chips_geo and the eyes (owned profile).

Writes material/light inventory and paired captures (vp2_*.png / eevee_*.png) of
cameras framing each target. The source scene is never saved.
"""
import hashlib,json,os,sys,time,traceback
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
PANEL='eeveeCompareModelPanel'
from eevee_maya import ui,viewport,exporter,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FRAME=float(os.environ.get('EEVEE_COMPARE_FRAME','1'))
S={'deadline':time.monotonic()+600,'shots':[],'i':0,'checks':{}};timers={}

def log(m):
 with open(OUT/'probe.log','a',encoding='utf-8') as f:f.write('%.3f %s\n'%(time.monotonic(),m))

def finish(error=None):
 for t in timers.values():t.stop()
 if error:log('ERROR '+error)
 S['checks']['source_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
 c=S.get('c')
 if c:
  for n in ('blender.log','maya_error.txt'):
   p=Path(c.engine.session)/n
   if p.exists():(OUT/n).write_bytes(p.read_bytes())
 (OUT/'result.json').write_text(json.dumps({'version':__version__,'error':error,'checks':S['checks'],'shots':S['shots'],
  'eevee_state':(c.engine.last_response.get('eevee_state') if c else None)},indent=2,default=str))
 try:ui.stop();viewport.deregister()
 except Exception:pass
 QtCore.QTimer.singleShot(300,lambda:cmds.quit(force=True))

def shading_of(mesh):
 sgs=cmds.listConnections(mesh,type='shadingEngine') or []
 out=[]
 for sg in sorted(set(sgs)):
  for plug in ('aiSurfaceShader','surfaceShader'):
   src=cmds.listConnections(sg+'.'+plug,source=True,destination=False) or []
   if src:out.append({'sg':sg,'plug':plug,'shader':src[0],'type':cmds.nodeType(src[0])})
 return out

def describe(shader):
 d={'type':cmds.nodeType(shader),'attrs':{},'connections':{}}
 for a in cmds.listAttr(shader,visible=True) or []:
  if '.' in a:continue
  try:
   v=cmds.getAttr(shader+'.'+a)
   if isinstance(v,(int,float,bool)):d['attrs'][a]=v
   elif isinstance(v,list) and len(v)==1 and isinstance(v[0],tuple) and len(v[0])==3:d['attrs'][a]=list(v[0])
  except Exception:pass
 conns=cmds.listConnections(shader,source=True,destination=False,connections=True,plugs=True) or []
 for dst,src in zip(conns[::2],conns[1::2]):
  node=src.split('.')[0];info={'from':src,'type':cmds.nodeType(node)}
  for f in ('fileTextureName','filename','colorSpace'):
   if cmds.attributeQuery(f,node=node,exists=True):info[f]=cmds.getAttr(node+'.'+f)
  d['connections'][dst.split('.',1)[1]]=info
 try:d['eevee_export']=exporter.material(shader)
 except Exception as e:d['eevee_export_error']=str(e)
 return d

def frame_camera(name,targets,distance=2.2,focal=50):
 boxes=[cmds.exactWorldBoundingBox(t) for t in targets]
 lo=[min(b[i] for b in boxes) for i in range(3)];hi=[max(b[i+3] for b in boxes) for i in range(3)]
 center=om.MVector(*[(lo[i]+hi[i])/2 for i in range(3)]);size=max(hi[i]-lo[i] for i in range(3))
 # View from the shot camera's direction so lighting matches the layout.
 src=S['shot_cam'];m=om.MMatrix(cmds.xform(src,query=True,worldSpace=True,matrix=True))
 back=om.MVector(m[8],m[9],m[10]).normal();pos=center+back*size*distance
 cam,shape=cmds.camera(name=name);cmds.setAttr(shape+'.focalLength',focal)
 cmds.setAttr(shape+'.nearClipPlane',max(.01,size*.01));cmds.setAttr(shape+'.farClipPlane',size*1000)
 cmds.setAttr(cam+'.translate',pos.x,pos.y,pos.z,type='double3')
 loc=cmds.spaceLocator()[0];cmds.setAttr(loc+'.translate',center.x,center.y,center.z,type='double3')
 con=cmds.aimConstraint(loc,cam,aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))[0];cmds.delete(con,loc)
 return cam

def grab(path):
 view=omui.M3dView.getM3dViewFromModelPanel(PANEL);view.refresh(False,True)
 im=om.MImage();view.readColorBuffer(im,True);im.writeToFile(str(path),'png')

def setup():
 def modal():
  w=QtWidgets.QApplication.activeModalWidget()
  if w:
   labels=[n.text() for n in w.findChildren(QtWidgets.QLabel)]
   b=next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text().replace('&','') in ('Allow','Allow All')),None)
   if b and 'eeveeBridge' in ' '.join(labels):b.click()
 obs=QtCore.QTimer();obs.timeout.connect(modal);obs.start(500);timers['obs']=obs
 cmds.loadPlugin((BRIDGE/'plug-ins/eeveeBridge.py').as_posix(),quiet=True)
 try:cmds.loadPlugin('mtoa',quiet=True)
 except Exception:log('mtoa not loaded')
 cmds.file(SOURCE.as_posix(),open=True,force=True,prompt=False,executeScriptNodes=False);obs.stop();ui.stop()
 cmds.currentTime(FRAME)
 mel.eval('setNamedPanelLayout "Single Perspective View"');cmds.modelEditor('modelPanel4',edit=True,allObjects=False)
 win=cmds.window('eeveeCompareWindow',widthHeight=(1280,800));cmds.paneLayout(configuration='single');cmds.modelPanel(PANEL,menuBarVisible=False);cmds.showWindow(win)
 view=omui.M3dView.getM3dViewFromModelPanel(PANEL);widget=wrapInstance(int(qtui.MQtUtil.findWindow(win)),QtWidgets.QWidget)
 for _ in range(2):QtWidgets.QApplication.processEvents();widget.resize(widget.width()+1280-view.portWidth(),widget.height()+720-view.portHeight())
 cams=[cmds.listRelatives(n,parent=True,fullPath=True)[0] for n in cmds.ls(type='camera',long=True) if not cmds.camera(n,query=True,startupCamera=True)]
 S['shot_cam']=cams[0] if cams else 'persp'
 meshes=[m for m in cmds.ls(type='mesh',long=True) if not cmds.getAttr(m+'.intermediateObject')]
 visible=[m for m in meshes if all(cmds.getAttr(p+'.visibility') for p in [m]+(cmds.listRelatives(m,allParents=True,fullPath=True) or []) if cmds.attributeQuery('visibility',node=p,exists=True))]
 chips=[m for m in visible if 'chips_geo' in m]
 eyes=[m for m in visible if any(k in m.split('|')[-1].lower() for k in ('pupil','sclera','iris','cornea','eyeball'))]
 inv={'chips':{m:shading_of(m) for m in chips},'eyes':{m:shading_of(m) for m in eyes}}
 inv['all']={m.split('|')[-1]:[(x['shader'],x['type'],x['plug']) for x in shading_of(m)] for m in visible}
 if os.environ.get('EEVEE_INVENTORY_ONLY'):
  (OUT/'inventory.json').write_text(json.dumps(inv,indent=2,default=str));finish();return
 shaders=sorted({s['shader'] for v in list(inv['chips'].values())+list(inv['eyes'].values()) for s in v})
 inv['shaders']={s:describe(s) for s in shaders}
 inv['lights']=[{'name':l,'type':cmds.nodeType(l)} for l in cmds.ls(lights=True,long=True)+(cmds.ls(type='aiSkyDomeLight',long=True) if 'aiSkyDomeLight' in cmds.allNodeTypes() else [])]
 for l in inv['lights']:
  if l['type']=='aiSkyDomeLight':
   l['texture']=exporter.environment_texture(l['name']) if hasattr(exporter,'environment_texture') else None
   l['attrs']={a:cmds.getAttr(l['name']+'.'+a) for a in ('intensity','aiExposure','camera','aiDiffuse','aiSpecular','format','resolution') if cmds.attributeQuery(a,node=l['name'],exists=True)}
 inv['color_management']=exporter.color_management()
 inv['hardwareRenderingGlobals']={a:cmds.getAttr('hardwareRenderingGlobals.'+a) for a in ('ssaoEnable','multiSampleEnable','ssrEnable','transparencyAlgorithm','lineAAEnable') if cmds.attributeQuery(a,node='hardwareRenderingGlobals',exists=True)}
 (OUT/'inventory.json').write_text(json.dumps(inv,indent=2,default=str));log('inventory %d chips %d eyes'%(len(chips),len(eyes)))
 S['checks']['found_chips']=bool(chips);S['checks']['found_eyes']=bool(eyes)
 shots=[('shot',None)]
 if chips:shots.append(('chips',frame_camera('CompareChipsCam',chips,1.6)))
 if eyes:shots.append(('eyes',frame_camera('CompareEyesCam',eyes,3.0,85)))
 S['plan']=shots
 S['pupils']=sorted({x['shader'] for m,v in inv['eyes'].items() if 'pupil' in m.lower() for x in v if x['type'] in ('standardSurface','aiStandardSurface')})
 cmds.modelEditor(PANEL,edit=True,displayLights='all',displayAppearance='smoothShaded',displayTextures=True,shadows=True,grid=False,lights=False,cameras=False,locators=False,nurbsCurves=False,manipulators=False,selectionHiliteDisplay=False,headsUpDisplay=False)
 cmds.select(clear=True)
 # 1) Viewport 2.0 captures
 for label,cam in shots:
  cmds.modelPanel(PANEL,edit=True,camera=cam or S['shot_cam'])
  for _ in range(4):QtWidgets.QApplication.processEvents();cmds.refresh(force=True)
  grab(OUT/('vp2_'+label+'.png'))
 log('vp2 captured')
 # 2) Eevee captures
 viewport.register();c=ui.attach(PANEL);c.engine.config.update(max_width=1920,adaptive_quality=False);S['c']=c
 S['i']=0;cmds.modelPanel(PANEL,edit=True,camera=shots[0][1] or S['shot_cam']);c.force=True;S['wait']=c.engine.sent_id;S['since']=time.monotonic()
 timers['tick']=QtCore.QTimer();timers['tick'].timeout.connect(tick);timers['tick'].start(200)

def tick():
 try:
  c=S['c']
  if time.monotonic()>S['deadline']:raise TimeoutError(c.engine.status)
  if c.startup_error or c.engine.last_response.get('error'):raise RuntimeError(c.startup_error or str(c.engine.last_response)[:3000])
  if time.monotonic()-S.get('hb',0)>2:
   S['hb']=time.monotonic();log('i=%d sent=%s recv=%s disp=%s force=%s status=%s'%(S['i'],c.engine.sent_id,c.engine.received_id,viewport.register().gpu_image.displayed_id,c.force,c.engine.status))
  if (c.force or not c.presented_once or c.engine.received_id<=S['wait'] or c.engine.sent_id!=c.engine.received_id
      or viewport.register().gpu_image.displayed_id!=c.engine.received_id or time.monotonic()-S['since']<2.5):return
  if c.engine.last_response.get('width')!=1920 and c.engine.last_response.get('interactive'):return
  label,cam=S['plan'][S['i']];grab(OUT/('eevee_'+label+'.png'))
  S['shots'].append({'label':label,'camera':cam,'response':{k:c.engine.last_response.get(k) for k in ('width','height','seconds','interactive')}})
  S['i']+=1
  if S['i']==len(S['plan']) and S.get('pupils') and not S.get('variant_done'):
   # Diagnostic variant (not saved): hide the iris colour to expose the reflection.
   S['variant_done']=True
   for sh in S['pupils']:cmds.setAttr(sh+'.base',0)
   S['plan'].append(('eyes_base0',[cam for l,cam in S['plan'] if l=='eyes'][0]))
  if S['i']==len(S['plan']):finish();return
  cmds.modelPanel(PANEL,edit=True,camera=S['plan'][S['i']][1]);c.force=True;S['wait']=c.engine.sent_id;S['since']=time.monotonic()
 except Exception:finish(traceback.format_exc())

def safe():
 try:setup()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe)
