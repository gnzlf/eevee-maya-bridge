"""Use Maya's real Renderer menu, option box, startup drawing and cancellation."""
import ctypes,hashlib,json,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from PySide2 import QtCore
from eevee_maya import ui,viewport,settings_window
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True);cmds.polyCube()
panel='modelPanel4';cmds.modelPanel(panel,edit=True,camera='persp')
cmds.setAttr('persp.translate',0,0,16,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
cmds.modelEditor(panel,edit=True,displayAppearance='smoothShaded',displayLights='default',grid=False)
cmds.select(clear=True);cmds.setFocus(panel);ui.install_menu()
menus=cmds.lsUI(menus=True,long=True) or []
renderer=next(m for m in menus if panel+'|' in m and 'buildRendererMenu' in str(cmds.menu(m,query=True,postMenuCommand=True)))
mel.eval(cmds.menu(renderer,query=True,postMenuCommand=True))
items=cmds.menu(renderer,query=True,itemArray=True)
eevee=next(i for i in items if cmds.menuItem(i,query=True,label=True)=='Eevee')
box=next(i for i in items if i.split('|')[-1]=='EeveeBridgeOptionBox')
default=next(i for i in items if i.split('|')[-1]=='OGSRenderer')
commands={key:cmds.menuItem(item,query=True,command=True) for key,item in [('eevee',eevee),('box',box),('default',default)]}
mel.eval(commands['box'])
checks={'native_option_box_exists':cmds.menuItem(box,query=True,optionBox=True),
        'options_open_without_starting_engine':ui._controller is None and cmds.window(settings_window.WINDOW,exists=True),
        'no_separate_viewer':not cmds.window(ui.WINDOW,exists=True),
        'legacy_activation_menu_removed':not any(cmds.menuItem(i,query=True,label=True) in ('Activar en viewport actual','Abrir panel independiente') for i in cmds.menu(ui.MENU,query=True,itemArray=True))}
settings_window._window.set_render_width('960');cmds.setFocus(panel);mel.eval(commands['eevee'])
view=omui.M3dView.getM3dViewFromModelPanel(panel);view.refresh(False,True)
state={'phase':0,'deadline':time.monotonic()+120,'checks':checks,'phases':[],'hashes':[],'started':time.monotonic()}
def screenshot(label):
    image=om.MImage();view.readColorBuffer(image,True);w,h=image.getSize();raw=ctypes.string_at(image.pixels(),w*h*4)
    image.writeToFile(str(root/'diagnostics'/('startup_'+label+'.png')),'png')
    return hashlib.sha256(raw).hexdigest()
def finish(error=None):
    timer.stop();(root/'diagnostics'/'native_startup_result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'phases':state['phases'],'hashes':state['hashes'],'error':error},indent=2))
def tick():
    try:
        if time.monotonic()>state['deadline']:raise TimeoutError(str(getattr(ui._controller,'engine',None)))
        c=ui._controller
        if state['phase']==0:
            if c is None:return
            loader=viewport.register().loading
            if loader.draws and not c.presented_once:
                state['phases'].append(loader.last_status.copy())
                if len(state['hashes'])<2:state['hashes'].append(screenshot('loading_'+str(len(state['hashes']))))
            if len(state['phases'])<3:return
            checks['loader_is_animated']=len({p['phase'] for p in state['phases']})>1
            checks['loading_frames_differ']=len(set(state['hashes']))==2
            state['old']=c;state['process']=c.engine.process
            cmds.setFocus(panel);mel.eval(commands['default']);state['phase']=1;state['switched']=time.monotonic();return
        if state['phase']==1:
            if time.monotonic()-state['switched']<.4:return
            checks['cancel_before_first_image_stops_engine']=c is None and state['process'].poll() is not None
            checks['cancel_stops_loading_timer']=not state['old'].loading_timer.isActive()
            checks['native_default_selection_preserved']=cmds.modelEditor(panel,query=True,rendererOverrideName=True)==''
            cmds.setFocus(panel);mel.eval(commands['eevee']);view.refresh(False,True);state['phase']=2;return
        if state['phase']==3:
            if c is not None:return
            state['blender']=ui.runtime_settings()['blender']
            ui.runtime_settings()['blender']=str(root/'diagnostics'/'missing-blender-test.exe')
            cmds.setFocus(panel);mel.eval(commands['eevee']);view.refresh(False,True);state['phase']=4;return
        if state['phase']==4:
            if c is None or not c.startup_error or not viewport.register().loading.last_status.get('error'):return
            checks['startup_failure_shown_in_viewport']=c.engine.process is None and viewport.register().loading.last_status['error']
            screenshot('failed');state['failed']=c
            ui.runtime_settings()['blender']=state['blender']
            cmds.setFocus(panel);mel.eval(commands['default']);state['phase']=5;return
        if state['phase']==5:
            if c is not None:return
            checks['failed_start_can_return_to_native']=not state['failed'].loading_timer.isActive() and cmds.modelEditor(panel,query=True,rendererOverrideName=True)==''
            cmds.modelEditor(panel,edit=True,displayAppearance='wireframe')
            cmds.setFocus(panel);mel.eval(commands['eevee']);view.refresh(False,True);state['phase']=6;return
        if state['phase']==6:
            if c is None or not c.presented_once or c.loading_timer.isActive():return
            checks['wireframe_start_finishes']=viewport.register().loading not in viewport.register().operations
            cmds.modelEditor(panel,edit=True,displayAppearance='smoothShaded');state['phase']=7;return
        if state['phase']==7:
            if c is None or not viewport.register().has_image or c.force or c.engine.sent_id!=c.engine.received_id:return
            checks['wireframe_returns_to_eevee_shading']=viewport.register().gpu_image.displayed_id==c.engine.received_id
            finish();return
        if c is None or not c.presented_once or c.force or c.engine.sent_id!=c.engine.received_id or c.loading_timer.isActive():return
        checks['native_renderer_starts_without_custom_window']=c.panel==panel and not cmds.window(ui.WINDOW,exists=True)
        checks['inactive_options_apply_on_start']=c.engine.config['max_width']==960
        checks['loader_removed_after_first_image']=viewport.register().loading not in viewport.register().operations
        checks['settings_stay_open']=cmds.window(settings_window.WINDOW,exists=True)
        settings_window._window.refresh();checks['settings_follow_running_controller']=settings_window._window.controller is c
        checks['gpu_error_free']=viewport.register().gpu_image.error is None
        screenshot('ready');cmds.setFocus(panel);mel.eval(commands['default']);state['phase']=3
    except Exception:finish(traceback.format_exc())
timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(100)
