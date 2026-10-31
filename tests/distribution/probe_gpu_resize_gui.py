"""Delay the first GPU import across several real producer resolution changes."""
import os,sys,time,json,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMayaUI as omui
import maya.utils
from PySide2 import QtCore
ROOT=Path(__file__).resolve().parents[2];OUTPUT=Path(os.environ['EEVEE_GPU_LIFETIME_PROBE']).resolve()
if Path(os.environ['MAYA_APP_DIR']).resolve()!=OUTPUT/'gpu_lifetime_profile':raise RuntimeError('Owned profile required')
sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import ui,viewport,native_controls,__version__
state={'deadline':time.monotonic()+120};checks={};reports={};timer=None
original=viewport.GPUImage.execute


def intercept(self,context):
    if not state.pop('inject',False):return original(self,context)
    c=state['controller'];engine=c.engine;old=dict(self.frame);delayed=[]
    self.release()
    def submit(width,height):
        request=c.snapshot('persp',width,height,native_controls.read(c.panel))
        engine.submit(request,force=True);target=engine.sent_id;deadline=time.monotonic()+20
        while engine.received_id<target:
            engine.poll()
            if time.monotonic()>deadline:raise TimeoutError('Producer resize timed out')
            time.sleep(.001)
        return dict(engine.frame)
    for width,height in ((1280,720),(1920,1080),(640,360),(1280,720)):
        delayed.append(old);old=submit(width,height)
    # Some old sizes can remain in the bounded reuse cache. The actual delayed
    # imports below verify ownership, rather than requiring a retirement layout.
    checks['unreleased_generations_retained']=engine.last_response['retired_gpu_pools']>0
    reports['delayed_sizes']=[[f['width'],f['height']] for f in delayed]
    for i,frame in enumerate(delayed):
        self.frame=frame;original(self,context)
        checks['delayed_import_%d_succeeds'%i]=self.displayed_id==frame['id'] and self.error is None
    self.release()
    engine.shared.acknowledge(max(f['id'] for f in delayed))
    submit(1280,720)
    checks['acknowledged_pools_are_released']=engine.last_response['retired_gpu_pools']==0
    self.frame=dict(engine.frame);original(self,context)
    checks['current_generation_still_draws']=self.displayed_id==engine.received_id and not self.error
    allocations=engine.last_response['gpu_resource_allocations']
    for width,height in ((640,360),(1280,720)):
        self.release();engine.shared.acknowledge(engine.received_id)
        self.frame=submit(width,height);original(self,context)
    checks['released_sizes_reuse_existing_gpu_resources']=engine.last_response['gpu_resource_allocations']==allocations and engine.last_response['gpu_resource_reuses']>=2
    checks['reused_generation_draws_current_frame']=self.displayed_id==engine.received_id and not self.error
    state['completed']=True


def finish(error=None):
    (OUTPUT/'result.json').write_text(json.dumps({'version':__version__,'passed':error is None and all(checks.values()) and state.get('completed',False),'checks':checks,'reports':reports,'error':error,'pid':os.getpid()},indent=2))
    viewport.GPUImage.execute=original;ui.stop();ui.remove_menu();viewport.deregister();QtCore.QTimer.singleShot(200,lambda:cmds.quit(force=True))


def tick():
    c=state['controller']
    if time.monotonic()>state['deadline']:timer.stop();finish('Startup timed out: '+c.engine.status);return
    if not c.presented_once or c.force or not c.engine.available:return
    timer.stop();c.timer.stop();c.in_tick=True;state['inject']=True
    try:
        omui.M3dView.getM3dViewFromModelPanel(c.panel).refresh(False,True)
        finish()
    except Exception:finish(traceback.format_exc())


def start():
    global timer
    cmds.file(new=True,force=True);cmds.polySphere()
    cmds.setAttr('persp.translate',0,0,8,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
    cmds.modelPanel('modelPanel4',edit=True,camera='persp');cmds.modelEditor('modelPanel4',edit=True,displayLights='default',grid=False)
    viewport.register();ui.install_menu();c=ui.attach('modelPanel4');c.engine.config.update(max_width=640,adaptive_quality=False,fast_navigation=False)
    state['controller']=c;viewport.GPUImage.execute=intercept;timer=QtCore.QTimer();timer.timeout.connect(tick);timer.start(150)
maya.utils.executeDeferred(start)
