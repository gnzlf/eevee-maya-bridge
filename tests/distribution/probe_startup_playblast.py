"""A playblast requested before startup completes must capture real frames."""
import hashlib,json,traceback
from pathlib import Path
import maya.cmds as cmds
from PySide2 import QtGui
from eevee_maya import ui
root=Path(__file__).resolve().parents[2]
if 'regression_profile' not in cmds.internalVar(userAppDir=True):raise RuntimeError('Dedicated regression Maya required')
ui.stop();cmds.file(new=True,force=True)
obj=cmds.polyCube()[0]
for frame,x in ((1,-3),(2,3)):cmds.setKeyframe(obj,attribute='translateX',time=frame,value=x)
cmds.setAttr('persp.translate',0,0,16,type='double3');cmds.setAttr('persp.rotate',0,0,0,type='double3')
panel='modelPanel4';cmds.modelPanel(panel,edit=True,camera='persp');cmds.modelEditor(panel,edit=True,displayLights='default',displayAppearance='smoothShaded',grid=False)
cmds.currentTime(1);cmds.select(clear=True);c=ui.attach(panel)
out=root/'diagnostics'/'startup-playblast';out.mkdir(exist_ok=True)
checks={'requested_before_engine_ready':not c.engine.ready}
results={};error=None
try:
    for mode in ('cold','warm'):
        cmds.playblast(format='image',compression='png',startTime=1,endTime=2,filename=str(out/mode),viewer=False,forceOverwrite=True,percent=100,widthHeight=(640,360),showOrnaments=False,offScreen=True,editorPanelName=panel)
        files=sorted(out.glob(mode+'.*.png'));pixels=[]
        for path in files:
            image=QtGui.QImage(str(path)).convertToFormat(QtGui.QImage.Format_RGBA8888)
            pixels.append(hashlib.sha256(bytes(image.bits())).hexdigest())
        results[mode]={'trace':list(c.capture_records),'hashes':pixels,'error':c.capture_error}
        checks[mode+'_exact_frames']=[r['maya_frame'] for r in c.capture_records]==[1,2]
        checks[mode+'_distinct_poses']=len(pixels)==2 and len(set(pixels))==2
        checks[mode+'_no_error']=c.capture_error is None
    checks['cold_images_match_warm_images']=results['cold']['hashes']==results['warm']['hashes']
except Exception:error=traceback.format_exc()
(root/'diagnostics'/'startup_playblast_result.json').write_text(json.dumps({'passed':not error and all(checks.values()),'checks':checks,'results':results,'error':error},indent=2))
