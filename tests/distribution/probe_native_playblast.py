"""Verify actual PNG and AVI frames under deliberate response latency."""
import hashlib,json,struct,time,traceback
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om
from PySide2 import QtCore,QtGui
from eevee_maya import ui,viewport,__version__
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True)
obj=cmds.polyCube()[0]
for frame,x in ((1,-3),(2,0),(3,3)):cmds.setKeyframe(obj,attribute='translateX',time=frame,value=x)
cmds.setAttr('persp.translate',0,0,16,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
cmds.modelPanel('modelPanel4',edit=True,camera='persp')
cmds.modelEditor('modelPanel4',edit=True,displayLights='default',displayAppearance='smoothShaded',grid=False)
cmds.currentTime(1);cmds.select(clear=True)
c=ui.attach('modelPanel4');c.engine.config['max_width']=320
out=root/'diagnostics'/'native-playblast';out.mkdir(exist_ok=True)
state={'deadline':time.monotonic()+90}
def avi_chunks(data,start=12,end=None):
    end=len(data) if end is None else end
    while start+8<=end:
        name=data[start:start+4];size=struct.unpack_from('<I',data,start+4)[0];body=start+8;stop=body+size
        if stop>end:break
        if name==b'LIST':yield from avi_chunks(data,body+4,stop)
        else:yield name,data[body:stop]
        start=stop+(size&1)
def run():
    if time.monotonic()>state['deadline']:
        timer.stop();raise TimeoutError(c.engine.status)
    if not c.presented_once or c.force or c.engine.received_id!=c.engine.sent_id:return
    timer.stop();checks={};results={};not_before={}
    original_poll,original_submit=c.engine.poll,c.engine.submit
    def submit(snapshot,force=False):
        sent=original_submit(snapshot,force)
        if sent:not_before[c.engine.sent_id]=time.monotonic()+.15
        return sent
    def poll():
        if time.monotonic()<not_before.get(c.engine.sent_id,0):return False
        return original_poll()
    c.engine.submit=submit;c.engine.poll=poll
    try:
        for label,format_,size in [('png320','image',(320,180)),('pngHD','image',(1920,1080)),('aviHD','avi',(1920,1080))]:
            start=time.monotonic()
            path=cmds.playblast(format=format_,compression='png' if format_=='image' else 'none',
                                startTime=1,endTime=3,filename=str(out/label),viewer=False,forceOverwrite=True,
                                percent=100,widthHeight=size,showOrnaments=False,offScreen=True,editorPanelName=c.panel)
            trace=list(c.capture_records)
            result={'returned':path,'trace':trace,'seconds':time.monotonic()-start,'capture_error':c.capture_error}
            checks[label+'_exact_poses']=[r['maya_frame'] for r in trace]==[1,2,3]
            checks[label+'_exact_size']=all((r['width'],r['height'])==size for r in trace)
            checks[label+'_waited_for_frames']=result['seconds']>=.44
            checks[label+'_no_capture_error']=c.capture_error is None
            if format_=='image':
                files=sorted(out.glob(label+'.*.png'))
                hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
                checks[label+'_three_distinct_files']=len(files)==3 and len(set(hashes))==3
                checks[label+'_image_dimensions']=all((QtGui.QImage(str(p)).width(),QtGui.QImage(str(p)).height())==size for p in files)
                result['hashes']=hashes
            else:
                video=Path(path) if path else out/(label+'.avi')
                if not video.exists():video=video.with_suffix('.avi')
                chunks=list(avi_chunks(video.read_bytes()))
                images=[data for name,data in chunks if name in (b'00db',b'00dc')]
                headers=[data for name,data in chunks if name==b'avih']
                checks[label+'_three_distinct_video_frames']=len(images)==3 and len({hashlib.sha256(d).hexdigest() for d in images})==3
                checks[label+'_video_header_count']=bool(headers) and struct.unpack_from('<I',headers[0],16)[0]==3
                checks[label+'_video_dimensions']=bool(headers) and struct.unpack_from('<II',headers[0],32)==size
                result['bytes']=video.stat().st_size;result['video_frames']=len(images)
            results[label]=result
        previous_timeout=c.engine.config.get('capture_timeout',120)
        c.engine.config['capture_timeout']=.02
        try:
            cmds.playblast(format='image',compression='png',startTime=1,endTime=1,filename=str(out/'mustfail'),
                           viewer=False,forceOverwrite=True,percent=100,widthHeight=(320,180),
                           showOrnaments=False,offScreen=True,editorPanelName=c.panel,throwOnError=True)
            checks['timeout_reported_or_native_error']=bool(c.capture_error)
        except RuntimeError:
            checks['timeout_reported_or_native_error']=True
        finally:c.engine.config['capture_timeout']=previous_timeout
        failed=list(out.glob('mustfail.*.png'))
        def red_failure(path):
            image=QtGui.QImage(str(path));color=image.pixelColor(image.width()//2,image.height()//2)
            return color.red()>100 and color.green()<40 and color.blue()<40
        checks['timeout_does_not_write_stale_image']=not failed or all(red_failure(p) for p in failed)
        checks['timeout_is_reported']=bool(c.capture_error)
    except Exception:state['error']=traceback.format_exc()
    finally:
        c.engine.poll=original_poll;c.engine.submit=original_submit
        (root/'diagnostics'/'native_playblast_result.json').write_text(json.dumps({
            'passed':not state.get('error') and all(checks.values()),'version':__version__,
            'checks':checks,'results':results,'error':state.get('error')},indent=2))
timer=QtCore.QTimer();timer.timeout.connect(run);timer.start(100)
