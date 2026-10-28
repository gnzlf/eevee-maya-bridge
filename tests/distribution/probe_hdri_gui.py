"""Native Maya captures: HDR radiance must reach reflective and diffuse materials."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import maya.cmds as cmds
import maya.utils
from PySide2 import QtCore, QtGui, QtWidgets
import maya.OpenMayaUI as omui
from shiboken2 import wrapInstance

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(os.environ['EEVEE_HDRI_PROBE']).resolve()
if Path(os.environ.get('MAYA_APP_DIR', '')).resolve() != OUTPUT/'hdri_regression_profile':
    raise RuntimeError('An owned HDRI regression profile is required')
sys.path.insert(0, str(ROOT/'scripts'))
from eevee_maya import ui, viewport, exporter, maya_lights, engine, settings_window, __version__
from eevee_maya.changes import SceneChanges
checks = {}; reports = {}; state = {'deadline': time.monotonic()+240}; timer = None


def fixture(path, swap=False):
    # Original synthetic lat-long HDR, radiance up to 12; no external assets.
    pixels = bytearray()
    for y in range(128):
        for x in range(256):
            u, v = x/256, y/128
            rgb = [.035, .025, .04]
            if .1 < u < .3 and .15 < v < .75: rgb = [8, .2, .05]
            if .57 < u < .72 and .3 < v < .85: rgb = [.05, .3, 12]
            if .4 < u < .55 and .1 < v < .25: rgb = [6, 6, 6]
            if swap: rgb = [rgb[2], rgb[0], rgb[1]]
            mantissa, exponent = math.frexp(max(rgb))
            scale = mantissa*256/max(rgb)
            pixels.extend(bytes([int(c*scale) for c in rgb]+[exponent+128]))
    path.write_bytes(b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 128 +X 256\n'+pixels)


def capture(label, width=960):
    c = state['controller']
    cmds.playblast(format='image', compression='png', startTime=1, endTime=1,
        filename=str(OUTPUT/label), viewer=False, forceOverwrite=True, percent=100,
        widthHeight=(width, width*9//16), showOrnaments=False, offScreen=True, editorPanelName=c.panel)
    image = QtGui.QImage(str(next(OUTPUT.glob(label+'.*.png')))).convertToFormat(QtGui.QImage.Format_RGBA8888)
    bits=image.constBits()
    if hasattr(bits,'setsize'):bits.setsize(image.byteCount())
    data=bytes(bits); values=[]
    scale=width//960
    for center in (192, 480, 768):
        region=[data[y*image.bytesPerLine()+x*4+k]/255 for y in range(220*scale,320*scale,scale) for x in range((center-50)*scale,(center+50)*scale,scale) for k in range(3)]
        values.append({'mean':sum(region)/len(region),'peak':max(region),
                       'variance':sum(v*v for v in region)/len(region)-(sum(region)/len(region))**2})
    checks[label+'_valid_capture'] = c.capture_error is None and bool(c.capture_records)
    reports[label] = {'spheres': values, 'environment': c.engine.last_response['eevee_state']['environment'],
                      'rebuilds': c.engine.last_response['scene_rebuilds'] if 'scene_rebuilds' in c.engine.last_response else None}
    state[label] = data
    return [v['mean'] for v in values]


def finish(error=None):
    timer.stop()
    (OUTPUT/'result.json').write_text(json.dumps({'version': __version__, 'passed': error is None and all(checks.values()),
        'checks': checks, 'reports': reports, 'error': error, 'pid': os.getpid()}, indent=2), encoding='utf-8')
    ui.stop(); ui.remove_menu(); viewport.deregister()
    QtCore.QTimer.singleShot(200, lambda: cmds.quit(force=True))


def tick():
    c = state['controller']
    if time.monotonic() > state['deadline']: finish('Startup timed out: '+c.engine.status); return
    if not c.presented_once or c.force or not c.engine.available: return
    timer.stop()
    try:
        dome=state['dome']; parent=state['parent']
        window=settings_window.SettingsWindow(c)
        cmds.tabLayout(window.tabs,edit=True,selectTab=window.hdri_tab)
        checks['native_settings_has_hdri_tab']='HDRI' in cmds.tabLayout(window.tabs,query=True,tabLabel=True)
        checks['settings_find_existing_dome_without_selecting_it']=window.hdri==dome
        bindings={attr:cmds.attrControlGrp(control,query=True,attribute=True) for attr,control in window.hdri_widgets.items()}
        reports['settings_bindings']=bindings
        checks['settings_bind_native_intensity_exposure_camera_resolution']=all(cmds.ls(plug.split('.')[0],long=True)[0]==dome and plug.split('.')[-1]==attr for attr,plug in bindings.items())
        window.show_hdri_background(False)
        checks['background_checkbox_changes_only_camera_visibility']=cmds.getAttr(dome+'.camera')==0 and cmds.getAttr(dome+'.intensity')==1
        cmds.setAttr(dome+'.camera',lock=True);window.refresh_hdri()
        checks['locked_native_background_disables_checkbox']=not cmds.checkBox(window.hdri_background,query=True,enable=True)
        cmds.setAttr(dome+'.camera',lock=False);window.refresh_hdri()
        checks['unlocked_native_background_enables_checkbox']=cmds.checkBox(window.hdri_background,query=True,enable=True)
        pointer=omui.MQtUtil.findWindow(window.window)
        wrapInstance(int(pointer),QtWidgets.QWidget).grab().save(str(OUTPUT/'hdri_settings.png'))
        cmds.setAttr(dome+'.intensity',0); dark=capture('zero')
        cmds.setAttr(dome+'.intensity',.15); lit=capture('lit')
        checks['hdri_lights_metal_rough_metal_and_matte'] = all(b>a+.03 for a,b in zip(dark,lit))
        checks['chrome_reflects_spatial_detail'] = reports['lit']['spheres'][0]['variance']>.01
        cmds.setAttr(dome+'.exposure',1); exposed=capture('exposure')
        checks['exposure_changes_all_materials'] = all(b>a+.015 for a,b in zip(lit,exposed))
        checks['exposure_reuses_world_shader_graph'] = reports['lit']['environment']['graph_rebuilds']==reports['exposure']['environment']['graph_rebuilds']
        cmds.setAttr(dome+'.exposure',0)
        cmds.setAttr(dome+'.camera',1); visible=capture('background')
        checks['camera_visibility_preserves_lighting_and_reflections'] = max(abs(a-b) for a,b in zip(lit,visible))<.01 and state['lit']!=state['background']
        cmds.setAttr(dome+'.camera',0)
        capture('background_hidden')
        changes=SceneChanges();changes.refresh_callbacks();changes.dirty=changes.structural=False
        cmds.setAttr(parent+'.rotateY',90)
        checks['dome_rotation_does_not_reexport_geometry'] = not changes.dirty and not changes.structural
        changes.close()
        rotated=capture('rotation')
        checks['rotation_moves_reflection'] = abs(rotated[0]-lit[0])>.01
        checks['rotation_reuses_world_shader_graph'] = reports['background_hidden']['environment']['graph_rebuilds']==reports['rotation']['environment']['graph_rebuilds']
        cmds.setAttr(parent+'.rotateY',0)
        full=capture('full_hd',1920)
        checks['full_hd_preserves_hdri_reflection']=max(abs(a-b) for a,b in zip(lit,full))<.02
        cmds.modelEditor(c.panel,edit=True,displayLights='active');cmds.select(parent)
        selected=capture('selected')
        checks['selected_dome_lights_scene'] = max(abs(a-b) for a,b in zip(lit,selected))<.01 and dome in maya_lights.selected()
        cmds.select(state['spheres'][0]); unselected=capture('unselected')
        checks['unselected_dome_does_not_leak'] = max(unselected)<.02
        cmds.modelEditor(c.panel,edit=True,displayLights='all');cmds.hide(parent)
        hidden=capture('hidden'); checks['hidden_dome_does_not_leak']=max(hidden)<.02
        cmds.showHidden(parent)
        file=state['file']; cmds.disconnectAttr(file+'.outColor',dome+'.color')
        ai=cmds.shadingNode('aiImage',asTexture=True)
        cmds.setAttr(ai+'.filename',str(OUTPUT/'fixture.hdr'),type='string')
        cmds.setAttr(ai+'.colorSpace','Raw',type='string');cmds.connectAttr(ai+'.outColor',dome+'.color')
        ai_lit=capture('ai_image');checks['ai_image_matches_file']=max(abs(a-b) for a,b in zip(lit,ai_lit))<.01
        cmds.setAttr(ai+'.filename',str(OUTPUT/'fixture.exr'),type='string')
        exr=capture('ai_image_exr');checks['exr_matches_hdr_radiance']=max(abs(a-b) for a,b in zip(lit,exr))<.01
        cmds.setAttr(ai+'.filename',str(OUTPUT/'fixture_swap.hdr'),type='string')
        swapped=capture('image_changed');checks['changing_hdri_updates_reflections']=state['ai_image']!=state['image_changed']
        cmds.setAttr(ai+'.filename',str(OUTPUT/'not_present.exr'),type='string')
        missing=capture('missing');checks['missing_map_does_not_become_white_light']=max(missing)<.02 and bool(reports['missing']['environment']['warnings'])
        cmds.setAttr(ai+'.filename',str(OUTPUT/'fixture.hdr'),type='string')
        recovered=capture('recovered');checks['missing_map_recovers_after_path_fix']=max(abs(a-b) for a,b in zip(lit,recovered))<.01
        cmds.disconnectAttr(ai+'.outColor',dome+'.color');cmds.setAttr(dome+'.color',.03,.06,.8,type='double3')
        constant=capture('constant');checks['constant_dome_supported']=min(constant)>.02
        second=cmds.shadingNode('aiSkyDomeLight',asLight=True)
        second_shape=cmds.listRelatives(second,shapes=True,fullPath=True)[0]
        cmds.setAttr(second_shape+'.color',.03,.06,.8,type='double3');cmds.setAttr(second_shape+'.intensity',.15);cmds.setAttr(second_shape+'.camera',0)
        summed=capture('two_domes');checks['multiple_domes_add_radiance']=all(b>a+.015 for a,b in zip(constant,summed))
        cmds.delete(second)
        cmds.setAttr(dome+'.camera',0);cmds.setAttr(dome+'.intensity',0)
        removed=capture('removed');checks['removing_hdri_removes_cached_reflection']=max(removed)<.02
        checks['gpu_transport_error_free']=viewport._override.gpu_image.error is None
        finish()
    except Exception: finish(traceback.format_exc())


def start():
    global timer
    cmds.file(new=True,force=True);cmds.loadPlugin('mtoa',quiet=True)
    fixture(OUTPUT/'fixture.hdr');fixture(OUTPUT/'fixture_swap.hdr',True)
    subprocess.run([engine.settings()['blender'],'-b','--factory-startup','--python-exit-code','1','--python',
        str(ROOT/'tests/distribution/probe_hdri_fixture.py'),'--',str(OUTPUT)],
        check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
    spheres=[]
    for x,kind,roughness in ((-3,'aiStandardSurface',0),(0,'standardSurface',.4),(3,'lambert',.8)):
        sphere=cmds.polySphere(radius=1,subdivisionsX=48,subdivisionsY=32)[0];spheres.append(sphere)
        cmds.setAttr(sphere+'.translateX',x)
        mat=cmds.shadingNode(kind,asShader=True)
        if kind!='lambert':
            cmds.setAttr(mat+'.baseColor',.7,.7,.7,type='double3');cmds.setAttr(mat+'.metalness',1);cmds.setAttr(mat+'.specularRoughness',roughness)
        else:cmds.setAttr(mat+'.color',.5,.5,.5,type='double3')
        sg=cmds.sets(renderable=True,noSurfaceShader=True,empty=True);cmds.connectAttr(mat+'.outColor',sg+'.surfaceShader');cmds.sets(sphere,edit=True,forceElement=sg)
    parent=cmds.shadingNode('aiSkyDomeLight',asLight=True)
    dome=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
    file=cmds.shadingNode('file',asTexture=True)
    cmds.setAttr(file+'.fileTextureName',str(OUTPUT/'fixture.hdr'),type='string');cmds.setAttr(file+'.colorSpace','Raw',type='string')
    cmds.connectAttr(file+'.outColor',dome+'.color');cmds.setAttr(dome+'.camera',0)
    cmds.setAttr('persp.translate',0,0,14,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
    cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',10)
    cmds.modelPanel('modelPanel4',edit=True,camera='persp')
    cmds.modelEditor('modelPanel4',edit=True,displayLights='all',grid=False,shadows=False,displayAppearance='smoothShaded',lights=False,manipulators=False,selectionHiliteDisplay=False)
    cmds.select(clear=True);viewport.register();ui.install_menu();c=ui.attach('modelPanel4')
    c.engine.config.update(max_width=640,adaptive_quality=False)
    state.update(controller=c,dome=dome,parent=parent,file=file,spheres=spheres)
    timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)


maya.utils.executeDeferred(start)
