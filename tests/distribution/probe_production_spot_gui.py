"""Production spotlight regression; the caller explicitly supplies a scene path."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.utils
from PySide2 import QtCore,QtGui
ROOT=Path(os.environ.get('EEVEE_INSTALLED_ROOT',Path(__file__).resolve().parents[2]));OUTPUT=Path(os.environ['EEVEE_PRODUCTION_SPOT_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUTPUT/'production_spot_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__
SOURCE=Path(os.environ['EEVEE_PRODUCTION_SCENE']);original_sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
state={'deadline':time.monotonic()+300};checks={};reports={};timer=None


def capture(label):
 c=state['controller'];frame=cmds.currentTime(query=True)
 cmds.playblast(format='image',compression='png',startTime=frame,endTime=frame,filename=str(OUTPUT/label),viewer=False,forceOverwrite=True,percent=100,widthHeight=(1920,1080),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
 image=QtGui.QImage(str(next(OUTPUT.glob(label+'.*.png')))).convertToFormat(QtGui.QImage.Format_RGBA8888)
 bits=image.constBits()
 if hasattr(bits,'setsize'):bits.setsize(image.byteCount())
 checks[label+'_valid_full_hd']=not c.capture_error and bool(c.capture_records) and (image.width(),image.height())==(1920,1080)
 response=c.engine.last_response
 reports[label]={'lights':response['eevee_state']['light_details'],'meshes':response['meshes'],'render_camera':response['render_camera']}
 return bytes(bits)


def finish(error=None):
 if timer:timer.stop()
 checks['source_scene_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==original_sha
 (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
 ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def tick():
 c=state['controller']
 if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
 if not c.presented_once or c.force or not c.engine.available:return
 timer.stop()
 try:
  spot=state['spot'];parent=state['parent']
  cmds.setAttr(spot+'.intensity',0);dark=capture('spot_zero')
  cmds.setAttr(spot+'.intensity',1);lit=capture('spot_one')
  cmds.setAttr(spot+'.intensity',8);bright=capture('spot_eight')
  cmds.setAttr(spot+'.useRayTraceShadows',True);cmds.modelEditor(c.panel,edit=True,shadows=True);shadow=capture('spot_shadows')
  sun=cmds.directionalLight();sun_parent=cmds.listRelatives(sun,parent=True,fullPath=True)[0]
  cmds.xform(sun_parent,worldSpace=True,matrix=cmds.xform(parent,query=True,worldSpace=True,matrix=True))
  cmds.select(sun_parent);reference=capture('directional_reference')
  # A surface mask from a separate directional-light reference excludes gray
  # background, UI icons and the small bright tile that hid the old regression.
  mask=[i for i in range(0,len(reference),4) if max(reference[i+k]-dark[i+k] for k in range(3))>40]
  checks['reference_contains_lit_surfaces']=len(mask)>10000
  def coverage(pixels,threshold):return sum(max(pixels[i+k]-dark[i+k] for k in range(3))>threshold for i in mask)/max(1,len(mask))
  reports['surface_coverage']={'pixels':len(mask),'intensity_one':coverage(lit,3),'intensity_eight':coverage(bright,15),'shadows':coverage(shadow,15)}
  checks['default_spot_illuminates_surfaces']=coverage(lit,3)>.7
  checks['intensity_changes_surface_brightness']=coverage(bright,15)>.8 and sum(bright[i] for i in mask)>sum(lit[i] for i in mask)*1.5
  checks['shadows_keep_surface_illumination']=coverage(shadow,15)>.7
  checks['eevee_keeps_perspective_classification']=reports['spot_one']['render_camera']['projection_kind']=='perspective'
  cmds.select(parent);cmds.currentTime(cmds.currentTime(query=True)+1);capture('next_frame')
  checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None
  finish()
 except Exception:finish(traceback.format_exc())


def start():
 global timer
 cmds.loadPlugin('mtoa',quiet=True);cmds.file(str(SOURCE),open=True,force=True,prompt=False,executeScriptNodes=False)
 cameras=[n for n in cmds.ls(type='camera',long=True) if not cmds.camera(n,query=True,startupCamera=True)]
 camera=next((n for n in cameras if cmds.getAttr(n+'.renderable')),cameras[0] if cameras else 'persp')
 selection=om.MSelectionList();selection.add(camera);path=selection.getDagPath(0)
 if path.node().hasFn(om.MFn.kTransform):path.extendToShape()
 spot=cmds.spotLight(name='EeveeSpotRegression');parent=cmds.listRelatives(spot,parent=True,fullPath=True)[0]
 cmds.xform(parent,worldSpace=True,matrix=list(path.inclusiveMatrix()))
 cmds.modelPanel('modelPanel4',edit=True,camera=camera)
 cmds.modelEditor('modelPanel4',edit=True,displayLights='active',grid=False,shadows=False,displayAppearance='smoothShaded',displayTextures=True,nurbsCurves=False,joints=False,locators=False,manipulators=False,cameras=False,lights=False,imagePlane=False,selectionHiliteDisplay=False)
 cmds.setAttr('hardwareRenderingGlobals.ssaoEnable',False)
 cmds.select(parent);viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=960,adaptive_quality=False)
 original_submit=c.engine.submit
 def submit(snapshot,*args,**kwargs):
  # Isolate surface illumination from the source scene's saved atmosphere.
  snapshot=dict(snapshot,effects=dict(snapshot['effects'],fog=False))
  return original_submit(snapshot,*args,**kwargs)
 c.engine.submit=submit
 state.update(controller=c,spot=spot,parent=parent);timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(200)
def safe_start():
 try:start()
 except Exception:finish(traceback.format_exc())
maya.utils.executeDeferred(safe_start)
