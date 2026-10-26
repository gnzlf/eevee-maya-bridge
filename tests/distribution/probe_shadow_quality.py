"""Render actual shadow presets and native switches in the isolated Maya fixture."""
import ctypes,json,math,statistics,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore
from eevee_maya import ui,viewport,settings_window,shadow_quality
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True)
mat=cmds.shadingNode('lambert',asShader=True);cmds.setAttr(mat+'.color',.65,.65,.65,type='double3')
sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader')
receiver=cmds.polyPlane(name='ShadowReceiver',width=18,height=12,axis=(0,0,1),subdivisionsX=1,subdivisionsY=1)[0]
cmds.sets(receiver,edit=True,forceElement=sg)
for i in range(24):
    bar=cmds.polyCube(name='ShadowSlat',width=.06,height=3,depth=.08)[0]
    cmds.setAttr(bar+'.translate',-4+i*.22,0,3,type='double3');cmds.setAttr(bar+'.rotateZ',20)
    cmds.sets(bar,edit=True,forceElement=sg)
sun=cmds.directionalLight(name='ShadowSun',intensity=1.5)
parent=cmds.listRelatives(sun,parent=True)[0];cmds.setAttr(parent+'.rotateY',-48)
cmds.setAttr(sun+'.useDepthMapShadows',True)
cmds.setAttr('persp.translate',0,0,18,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
for a,v in [('focalLength',35),('nearClipPlane',.1),('farClipPlane',1000),('depthOfField',False)]:cmds.setAttr('perspShape.'+a,v)
panel='modelPanel4';cmds.modelPanel(panel,edit=True,camera='persp')
cmds.modelEditor(panel,edit=True,displayLights='all',shadows=True,grid=False,displayAppearance='smoothShaded',wireframeOnShaded=False,lights=False,manipulators=False,selectionHiliteDisplay=False)
for a in ('ssaoEnable','bloomEnable'):cmds.setAttr('hardwareRenderingGlobals.'+a,False)
cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',True);cmds.setAttr('hardwareRenderingGlobals.multiSampleCount',8)
cmds.select(clear=True);c=ui.attach(panel);c.engine.config.update(max_width=1920,adaptive_quality=False,shadow_quality='low',shadow_pool_size='auto')
cmds.setAttr(ui.scene_settings(select=False)+'.volumetrics',False)
ui.show_settings();window=settings_window._window
state={'step':0,'wait':0,'deadline':time.monotonic()+240,'results':{},'pixels':{},'checks':{},'pid':c.engine.process.pid,'times':{}}
def preset(key):
    label=next(label for label,k in shadow_quality.LABELS if key==k)
    cmds.optionMenu(window.shadow_quality,edit=True,value=label);window.set_shadow_quality(label)
steps=[('low',None),('medium',lambda:preset('medium')),('high',lambda:preset('high')),
       ('ultra',lambda:preset('ultra')),('memory',lambda:window.set_shadow_pool('256 MB')),
       ('soft',lambda:cmds.setAttr(sun+'.lightAngle',4)),
       ('off',lambda:cmds.modelEditor(panel,edit=True,shadows=False)),
       ('restored',lambda:(window.set_shadow_pool('Automática según calidad'),preset('high'),cmds.setAttr(sun+'.lightAngle',0),cmds.modelEditor(panel,edit=True,shadows=True)))]
def capture(name):
    view=omui.M3dView.getM3dViewFromModelPanel(panel);view.refresh(False,True)
    image=om.MImage();view.readColorBuffer(image,True);w,h=image.getSize();raw=ctypes.string_at(image.pixels(),w*h*4)
    image.writeToFile(str(root/'diagnostics'/('shadow_'+name+'.png')),'png')
    pixels=bytes(raw[4*(y*w+x)] for y in range(h//5,4*h//5) for x in range(w//5,4*w//5))
    r=c.engine.last_response
    return {'state':r['eevee_state'],'seconds':r['seconds'],'warm_median_ms':statistics.median(state['times'][name][2:])*1000,'width':r['width'],'height':r['height'],'rebuilds':r['scene_rebuilds'],'pid':c.engine.process.pid},pixels
def diff(a,b):
    return sum(abs(x-y) for x,y in zip(state['pixels'][a],state['pixels'][b]))/len(state['pixels'][a])
def finish(error=None):
    timer.stop();m=state['results'];checks=state['checks']
    if not error:
        checks.update(all_presets_rendered=all(m[k]['state']['shadow_quality']['preset']==k for k in ('low','medium','high','ultra')),
                      hd_shadows_double_previous_resolution=m['high']['state']['shadow_quality']['resolution']==1,
                      resolution_changes_image=diff('low','high')>.02,
                      override_memory_honored=m['memory']['state']['shadow_quality']['pool']=='256',
                      native_shadow_switch_changes_image=diff('memory','off')>1,
                      native_shadow_switch_synced=not m['off']['state']['shadows'],
                      native_sun_angle_honored=abs(m['soft']['state']['light_details'][0]['shadow_angle']-math.radians(4))<1e-6,
                      native_sun_angle_changes_image=diff('memory','soft')>.1,
                      restore_repeatable=diff('high','restored')<.1,
                      no_restart=all(v['pid']==state['pid'] for v in m.values()),
                      no_geometry_rebuild=all(v['rebuilds']==m['low']['rebuilds'] for v in m.values()),
                      preferences_saved=cmds.optionVar(query='eeveeShadowQuality')=='high' and cmds.optionVar(query='eeveeShadowPoolSize')=='auto',
                      full_resolution_preserved=all(v['width']==1920 for v in m.values()),
                      gpu_error_free=viewport.register().gpu_image.error is None)
        window.set_shadow_pool('256 MB')
        ui.stop();restored=ui.attach(panel)
        checks['preferences_restored_by_new_controller']=(restored.engine.config['shadow_quality']=='high'
                                                        and restored.engine.config['shadow_pool_size']=='256')
        restored.engine.config['shadow_pool_size']='auto';cmds.optionVar(stringValue=('eeveeShadowPoolSize','auto'))
    (root/'diagnostics'/'shadow_quality_result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'results':m,'image_difference':diff('low','high') if 'high' in m else None,'error':error},indent=2))
def tick():
    try:
        if time.monotonic()>state['deadline']:raise TimeoutError(c.engine.status)
        if c.force or c.engine.received_id<=state['wait'] or c.engine.received_id!=c.engine.sent_id:return
        if viewport.register().gpu_image.displayed_id!=c.engine.received_id:return
        name,_=steps[state['step']]
        state['wait']=c.engine.received_id
        times=state['times'].setdefault(name,[]);times.append(c.engine.last_response['seconds'])
        if len(times)<8:c.force=True;return
        state['results'][name],state['pixels'][name]=capture(name)
        state['wait']=c.engine.received_id;state['step']+=1
        if state['step']==len(steps):finish();return
        steps[state['step']][1]();c.force=True
    except Exception:finish(traceback.format_exc())
timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(200)
