"""Real native Maya/Eevee captures for area and ambient light edits."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore, QtGui

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=Path(os.environ['EEVEE_LIGHT_PROBE']).resolve()
PROFILE=OUTPUT/'light_regression_profile'
if Path(os.environ.get('MAYA_APP_DIR','')).resolve()!=PROFILE:
    raise RuntimeError('An owned light regression profile is required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,__version__,exporter,maya_lights
checks={};reports={};state={'deadline':time.monotonic()+240};timer=None


def capture(label):
    c=state['controller']
    cmds.playblast(format='image',compression='png',startTime=1,endTime=1,
        filename=str(OUTPUT/label),viewer=False,forceOverwrite=True,percent=100,
        widthHeight=(1920,1080),showOrnaments=False,offScreen=True,editorPanelName=c.panel)
    image=QtGui.QImage(str(next(OUTPUT.glob(label+'.*.png'))))
    colors=[image.pixelColor(image.width()//2+120+x,image.height()//2+80+y)
            for x in range(-4,5) for y in range(-4,5)]
    rgb=[sum(getattr(p,channel)() for p in colors)/len(colors)/255 for channel in ('red','green','blue')]
    checks[label+'_valid_full_hd']=c.capture_error is None and bool(c.capture_records) and (image.width(),image.height())==(1920,1080)
    reports[label]={'rgb':rgb,'lights':c.engine.last_response['eevee_state']['light_details']}
    return rgb


def finish(error=None):
    timer.stop()
    (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()),
        'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2),encoding='utf-8')
    ui.stop();ui.remove_menu();viewport.deregister()
    QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def tick():
    c=state['controller']
    if time.monotonic()>state['deadline']:finish('Startup timed out: '+c.engine.status);return
    if not c.presented_once or c.force or not c.engine.available:return
    timer.stop()
    try:
        area=state['area'];parent=cmds.listRelatives(area,parent=True,fullPath=True)[0]
        cmds.setAttr(area+'.intensity',0);dark=capture('area_zero')
        cmds.setAttr(area+'.intensity',1);lit=capture('area_one')
        checks['native_area_intensity_lights_geometry']=max(lit)>max(dark)+.1
        cmds.setAttr(parent+'.rotateY',180);back=capture('area_back')
        checks['native_area_direction_is_one_sided']=max(back)<max(lit)*.2
        cmds.setAttr(parent+'.rotateY',0)
        cmds.setAttr(parent+'.scale',3,2,1,type='double3')
        normalized=capture('area_scaled_normalized')
        cmds.setAttr(area+'.normalize',False);unnormalized=capture('area_scaled_unnormalized')
        checks['area_normalize_and_scale_change_energy']=max(unnormalized)>max(normalized)+.02 and reports['area_scaled_unnormalized']['lights'][0]['energy']>reports['area_scaled_normalized']['lights'][0]['energy']*20
        spec=next(l for l in exporter.lights() if l['name']==area)
        checks['area_dimensions_exported']=abs(spec['size_x']-6)<1e-6 and abs(spec['size_y']-4)<1e-6
        cmds.hide(parent)
        arnold=cmds.shadingNode('aiAreaLight',asLight=True)
        arnold_shape=cmds.listRelatives(arnold,shapes=True,fullPath=True)[0]
        cmds.setAttr(arnold+'.translateZ',3)
        cmds.setAttr(arnold_shape+'.intensity',5)
        cmds.setAttr(arnold_shape+'.color',.02,.05,1,type='double3')
        rgb=capture('arnold_area')
        checks['arnold_area_is_detected_and_lights_geometry']=rgb[2]>.15 and rgb[2]>rgb[0]*1.5
        cmds.select(arnold);cmds.modelEditor(c.panel,edit=True,displayLights='active')
        active=capture('arnold_area_active')
        checks['arnold_area_native_active_selection']=max(abs(a-b) for a,b in zip(rgb,active))<.02 and arnold_shape in maya_lights.selected()
        cmds.modelEditor(c.panel,edit=True,displayLights='all');cmds.hide(arnold)
        ambient=cmds.ambientLight(ambientShade=0,intensity=.6,rgb=(.02,.05,1))
        ambient_shape=cmds.ls(ambient,long=True)[0]
        rgb=capture('ambient_blue')
        checks['ambient_light_reaches_material']=rgb[2]>.2 and rgb[2]>rgb[0]*1.5
        cmds.setAttr(ambient+'.intensity',0);zero=capture('ambient_zero')
        checks['ambient_intensity_zero_removes_light']=max(zero)<.02
        cmds.setAttr(ambient+'.intensity',.6)
        ambient_parent=cmds.listRelatives(ambient,parent=True,fullPath=True)[0]
        cmds.setAttr(ambient_parent+'.translate',10,4,8,type='double3')
        moved=capture('ambient_moved')
        checks['shade_zero_is_independent_of_position']=max(abs(a-b) for a,b in zip(rgb,moved))<.01
        cmds.lightlink(light=ambient,object=state['plane'],b=True)
        unlinked=capture('ambient_unlinked')
        checks['ambient_light_link_excludes_receiver']=max(unlinked)<.02
        cmds.lightlink(light=ambient,object=state['plane'],make=True)
        cmds.select(ambient_parent);cmds.modelEditor(c.panel,edit=True,displayLights='active')
        selected=capture('ambient_active')
        checks['ambient_native_active_selection']=selected[2]>.2
        cmds.select(state['plane']);none=capture('ambient_not_active')
        checks['unselected_ambient_does_not_leak_or_enable_headlight']=max(none)<.02 and not any(l['name']=='EeveeDefaultHeadlight' for l in reports['ambient_not_active']['lights'])
        cmds.modelEditor(c.panel,edit=True,displayLights='all',useDefaultMaterial=True)
        default=capture('ambient_default_material')
        checks['ambient_supports_native_default_material']=default[2]>.2
        cmds.modelEditor(c.panel,edit=True,useDefaultMaterial=False)
        cmds.setAttr(ambient_parent+'.translate',0,0,3,type='double3')
        cmds.setAttr(ambient+'.ambientShade',1)
        shaded=capture('ambient_shade_one')
        cmds.setAttr(ambient_parent+'.translateZ',-3)
        back=capture('ambient_shade_one_back')
        checks['ambient_shade_changes_illumination']=shaded[2]>.02 and max(back)<.02
        cmds.setAttr(ambient_parent+'.translateZ',3)
        cmds.setAttr(ambient+'.color',1,1,1,type='double3')
        white=capture('ambient_shade_one_white')
        cmds.setAttr(ambient+'.intensity',5)
        strong=capture('ambient_shade_one_strong')
        checks['ambient_directional_intensity_changes_render']=max(strong)>max(white)+.1
        checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None
        finish()
    except Exception:finish(traceback.format_exc())


def start():
    global timer
    cmds.file(new=True,force=True);cmds.loadPlugin('mtoa',quiet=True)
    plane=cmds.polyPlane(width=4,height=4,axis=(0,0,1))[0]
    material=cmds.shadingNode('lambert',asShader=True)
    cmds.setAttr(material+'.color',.5,.5,.5,type='double3')
    sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True)
    cmds.connectAttr(material+'.outColor',sg+'.surfaceShader');cmds.sets(plane,edit=True,forceElement=sg)
    area=cmds.shadingNode('areaLight',asLight=True);shape=cmds.listRelatives(area,shapes=True,fullPath=True)[0]
    cmds.setAttr(area+'.translateZ',3);cmds.setAttr(shape+'.useRayTraceShadows',False)
    cmds.setAttr('persp.translate',0,0,12,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
    cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',6)
    cmds.modelPanel('modelPanel4',edit=True,camera='persp')
    cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,manipulators=False,selectionHiliteDisplay=False)
    cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4')
    c.engine.config.update(max_width=640,adaptive_quality=False)
    state.update(controller=c,area=shape,plane=plane)
    timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)


maya.utils.executeDeferred(start)
