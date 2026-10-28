"""Native captures of token UDIM paths; production input is optional and read-only."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore,QtGui
ROOT=Path(__file__).resolve().parents[2];OUTPUT=Path(os.environ['EEVEE_UDIM_PROBE']).resolve()
if Path(os.environ.get('MAYA_APP_DIR','')).resolve()!=OUTPUT/'udim_regression_profile':raise RuntimeError('Owned UDIM profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,exporter,__version__
checks={};reports={};state={'deadline':time.monotonic()+300};timer=None


def capture(label):
 c=state['controller']
 frame=cmds.currentTime(query=True)
 cmds.playblast(format='image',compression='png',startTime=frame,endTime=frame,filename=str(OUTPUT/label),viewer=False,forceOverwrite=True,percent=100,widthHeight=(1920,1080),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
 image=QtGui.QImage(str(next(OUTPUT.glob(label+'.*.png'))))
 def rgb(x,y):
  colors=[image.pixelColor(x+i,y+j) for i in range(-8,9) for j in range(-8,9)]
  return [sum(getattr(p,channel)() for p in colors)/len(colors) for channel in ('red','green','blue')]
 checks[label+'_valid_full_hd']=not c.capture_error and bool(c.capture_records) and image.width()==1920 and image.height()==1080
 reports[label]={'left':rgb(480,540),'right':rgb(1440,540),'face':rgb(690,650),'cloth':rgb(720,990),'scene_rebuilds':c.engine.last_response['scene_rebuilds']}
 return reports[label]


def finish(error=None):
 timer.stop()
 if state.get('source'):checks['production_scene_unchanged']=hashlib.sha256(state['source'].read_bytes()).hexdigest()==state['sha']
 (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2),encoding='utf-8')
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def tick():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  token=capture('literal_token')
  checks['udim_1001_has_warm_color']=token['left'][0]>token['left'][2]+30
  checks['udim_1002_has_purple_color']=token['right'][2]>token['right'][0]+30
  cmds.setAttr(state['file']+'.fileTextureName',str(OUTPUT/'texture_1001.png'),type='string')
  concrete=capture('concrete_tile')
  checks['literal_and_concrete_paths_match']=max(abs(a-b) for field in ('left','right') for a,b in zip(token[field],concrete[field]))<1
  path=os.environ.get('EEVEE_PRODUCTION_SCENE')
  if path:
   ui.stop();state['source']=Path(path);state['sha']=hashlib.sha256(state['source'].read_bytes()).hexdigest()
   cmds.loadPlugin('mtoa',quiet=True);cmds.file(path,open=True,force=True,prompt=False,executeScriptNodes=False);cmds.currentTime(2)
   cameras=[n for n in cmds.ls(type='camera',long=True) if cmds.getAttr(n+'.renderable') and not cmds.camera(n,query=True,startupCamera=True)]
   cmds.modelPanel('modelPanel4',edit=True,camera=cameras[0] if cameras else 'persp')
   configure_panel();c=ui.attach('modelPanel4');c.engine.config.update(max_width=960,adaptive_quality=False);state['controller']=c
   # Capture synchronizes even the cold renderer; do not rely on interactive FPS.
   production=capture('production_fixed')
   materials={name:exporter.material(name) for name in cmds.ls(type=['aiStandardSurface','standardSurface','lambert','blinn','phong'])}
   textures=[m['color_texture'] for m in materials.values() if m.get('color_texture') and '<UDIM>' in m['color_texture'].get('udim_pattern','')]
   checks['production_has_resolved_udim_materials']=bool(textures) and all(t['tiles'] and Path(t['path']).is_file() for t in textures)
   reports['production_texture_sets']=[{'tiles':t['tiles']} for t in textures]
   checks['production_skin_is_lit_and_warm']=production['face'][0]>40 and production['face'][0]>production['face'][2]+5
   checks['production_cloth_is_not_black']=max(production['cloth'])>30
  checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())


def configure_panel():
 cmds.modelEditor('modelPanel4',edit=True,displayLights='default',grid=False,shadows=False,displayAppearance='smoothShaded',displayTextures=True,nurbsCurves=False,joints=False,locators=False,manipulators=False,selectionHiliteDisplay=False)


def start():
 global timer
 cmds.file(new=True,force=True)
 for tile,color in ((1001,(220,120,65)),(1002,(65,30,220))):
  image=QtGui.QImage(16,16,QtGui.QImage.Format_RGB32);image.fill(QtGui.QColor(*color));image.save(str(OUTPUT/('texture_%d.png'%tile)))
 mat=cmds.shadingNode('lambert',asShader=True);sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader')
 file=cmds.shadingNode('file',asTexture=True);cmds.setAttr(file+'.fileTextureName',str(OUTPUT/'texture_<UDIM>.png'),type='string');cmds.setAttr(file+'.uvTilingMode',3);cmds.setAttr(file+'.colorSpace','sRGB',type='string');cmds.connectAttr(file+'.outColor',mat+'.color')
 for x,offset in ((-2,0),(2,1)):
  plane=cmds.polyPlane(width=3,height=3,axis=(0,0,1))[0];cmds.setAttr(plane+'.translateX',x);cmds.sets(plane,edit=True,forceElement=sg)
  if offset:cmds.polyEditUV(plane+'.map[*]',uValue=offset,vValue=0)
 cmds.setAttr('persp.translate',0,0,12,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3');cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',8)
 cmds.modelPanel('modelPanel4',edit=True,camera='persp');configure_panel();cmds.select(clear=True)
 viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False)
 state.update(controller=c,file=file);timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)


maya.utils.executeDeferred(start)
