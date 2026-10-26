"""Real GPU checks for matte Lambert, per-face colors and an eye shell."""
import ctypes,json,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore,QtGui
from eevee_maya import ui,viewport,exporter
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True)
def material(name,kind,color):
    mat=cmds.shadingNode(kind,asShader=True,name=name)
    cmds.setAttr(mat+('.baseColor' if kind=='standardSurface' else '.color'),*color,type='double3')
    sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader')
    return mat,sg
mat,sg=material('MatteIris','lambert',(.02,.7,.03))
inner=cmds.polySphere(radius=1.5,subdivisionsX=32,subdivisionsY=16)[0];cmds.sets(inner,edit=True,forceElement=sg)
glass,glass_sg=material('EyeShell','standardSurface',(.7,.7,.7))
cmds.setAttr(glass+'.transmission',1);cmds.setAttr(glass+'.specular',0)
outer=cmds.polySphere(radius=1.58,subdivisionsX=32,subdivisionsY=16)[0];cmds.sets(outer,edit=True,forceElement=glass_sg)
face,face_sg=material('PerFaceSkin','lambert',(.6,.2,.08))
patch=cmds.polyPlane(width=3,height=3,axis=(0,0,1),subdivisionsX=2,subdivisionsY=1)[0];cmds.setAttr(patch+'.translateX',-4)
cmds.sets(patch,edit=True,forceElement=face_sg);cmds.sets(patch+'.f[1]',edit=True,forceElement=sg)
glint,glint_sg=material('SpecularMask','standardSurface',(0,0,0));cmds.setAttr(glint+'.specularRoughness',.3)
mask=QtGui.QImage(8,8,QtGui.QImage.Format_RGB32)
for y in range(8):
    for x in range(8):mask.setPixelColor(x,y,QtGui.QColor(0,0,0) if x<4 else QtGui.QColor(255,255,255))
mask_path=root/'diagnostics'/'material_specular_mask.png';mask.save(str(mask_path))
file=cmds.shadingNode('file',asTexture=True);cmds.setAttr(file+'.fileTextureName',str(mask_path),type='string')
cmds.connectAttr(file+'.outColor',glint+'.specularColor')
gloss_patch=cmds.polyPlane(width=3,height=3,axis=(0,0,1),subdivisionsX=1,subdivisionsY=1)[0];cmds.setAttr(gloss_patch+'.translateX',4)
cmds.sets(gloss_patch,edit=True,forceElement=glint_sg)
panel='modelPanel4';cmds.setAttr('persp.translate',0,0,18,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
cmds.setAttr('perspShape.focalLength',35);cmds.setAttr('perspShape.nearClipPlane',.1)
cmds.modelPanel(panel,edit=True,camera='persp');cmds.modelEditor(panel,edit=True,displayLights='default',shadows=False,grid=False,depthOfFieldPreview=False,displayTextures=True,useDefaultMaterial=False,selectionHiliteDisplay=False)
for a in ('ssaoEnable','bloomEnable'):cmds.setAttr('hardwareRenderingGlobals.'+a,False)
cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',True);cmds.setAttr('hardwareRenderingGlobals.multiSampleCount',8)
cmds.select(clear=True);c=ui.attach(panel);c.engine.config.update(max_width=1920,adaptive_quality=False)
cmds.setAttr(ui.scene_settings(select=False)+'.volumetrics',False)
state={'step':0,'wait':0,'deadline':time.monotonic()+180,'results':{},'checks':{}}
steps=[('clear',None),('opaque',lambda:cmds.setAttr(glass+'.transmission',0)),
       ('restore',lambda:cmds.setAttr(glass+'.transmission',1)),
       ('default',lambda:cmds.modelEditor(panel,edit=True,useDefaultMaterial=True)),
       ('original',lambda:cmds.modelEditor(panel,edit=True,useDefaultMaterial=False))]
def capture(name):
    view=omui.M3dView.getM3dViewFromModelPanel(panel);view.refresh(False,True)
    image=om.MImage();view.readColorBuffer(image,True);w,h=image.getSize();raw=ctypes.string_at(image.pixels(),w*h*4)
    image.writeToFile(str(root/'diagnostics'/('material_probe_'+name+'.png')),'png')
    def sample(x,y):
        px,py,_=view.worldToView(om.MPoint(x,y,0));pixels=[raw[4*(iy*w+ix):4*(iy*w+ix)+3] for iy in range(py-5,py+5) for ix in range(px-5,px+5)]
        return [sum(p[i] for p in pixels)/len(pixels) for i in range(3)]
    return {'center':sample(0,0),'left':sample(-4.8,0),'right':sample(-3.2,0),
            'specular_left':sample(3.2,0),'specular_right':sample(4.8,0),
            'state':c.engine.last_response['eevee_state'],'width':c.engine.last_response['width']}
def finish(error=None):
    timer.stop();m=state['results'];checks=state['checks']
    if not error:
        checks.update(lambert_has_no_specular=exporter.material(mat)['specular_weight']==0,
                      specular_texture_exported=exporter.material(glint)['specular_color_texture'] is not None,
                      specular_mask_changes_reflection=abs(m['clear']['specular_left'][0]-m['clear']['specular_right'][0])>10,
                      specular_mask_black_stays_black=min(m['clear']['specular_left'][0],m['clear']['specular_right'][0])<5,
                      iris_visible_through_shell=m['clear']['center'][1]>m['clear']['center'][0]*2,
                      opaque_shell_hides_iris=abs(m['opaque']['center'][1]-m['opaque']['center'][0])<5,
                      transmission_change_restores_iris=max(abs(a-b) for a,b in zip(m['clear']['center'],m['restore']['center']))<1,
                      per_face_skin_visible=m['clear']['left'][0]>m['clear']['left'][1]*1.2,
                      per_face_iris_visible=m['clear']['right'][1]>m['clear']['right'][0]*2,
                      default_material_overrides_shell=abs(m['default']['center'][1]-m['default']['center'][0])<5,
                      default_material_restores_source=max(abs(a-b) for a,b in zip(m['clear']['center'],m['original']['center']))<1,
                      full_resolution_preserved=all(x['width']==1920 for x in m.values()),
                      gpu_error_free=viewport.register().gpu_image.error is None)
    (root/'diagnostics'/'material_translation_result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'results':m,'error':error},indent=2))
def tick():
    try:
        if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
        if c.force or c.engine.received_id<=state['wait'] or c.engine.received_id!=c.engine.sent_id:return
        if viewport.register().gpu_image.displayed_id!=c.engine.received_id:return
        name,_=steps[state['step']];state['results'][name]=capture(name);state['wait']=c.engine.received_id;state['step']+=1
        if state['step']==len(steps):finish();return
        steps[state['step']][1]();c.force=True
    except Exception:finish(traceback.format_exc())
timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(200)
