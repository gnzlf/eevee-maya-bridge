"""Mayapy: cached geometry must remain exact after edits, undo and reveal."""
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
profile=tempfile.TemporaryDirectory(prefix='Eevee-mesh-cache-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
sys.path.insert(0,str(ROOT/'scripts'))
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds
import maya.api.OpenMaya as om
from eevee_maya.scene_stream import SceneStream
from eevee_maya.mesh_packet import records
from eevee_maya import exporter
checks={};stream=None;points=None


def path_of(obj):
    selected=om.MSelectionList();selected.add(cmds.listRelatives(obj,shapes=True,noIntermediate=True,fullPath=True)[0])
    return selected.getDagPath(0)


def update(initial=False):
    global points
    rows=list(records(stream.update(initial)))
    for row in rows:
        if 'points' in row:points=row['points'].cast('f').tolist()
    fn=om.MFnMesh(path)
    if path.isVisible() and fn.findPlug('displaySmoothMesh',False).asInt():
        fn=om.MFnMesh(fn.findPlug('outSmoothMesh',False).asMObject())
    expected=[v for p in fn.getPoints() for v in (p.x,p.y,p.z)]
    return len(points)==len(expected) and all(abs(a-b)<1e-5 for a,b in zip(points,expected)),rows


try:
    cube=cmds.polyCube()[0];path=path_of(cube);shape=path.fullPathName()
    stream=SceneStream([shape]);stream.dll.es_evaluations.argtypes=[ctypes.c_void_p]
    checks['initial_geometry']=update(True)[0]
    valid,rows=update();checks['unchanged_geometry_is_not_evaluated']=valid and not rows and stream.dll.es_evaluations(stream.pointer)==0
    cmds.setAttr(cube+'.translateX',2);valid,rows=update()
    checks['transform_only_keeps_cached_points']=valid and len(rows)==1 and rows[0]['flags']==1
    cmds.move(.5,0,0,cube+'.vtx[0]',relative=True);checks['component_edit']=update()[0]
    cmds.undo();checks['undo_component_edit']=update()[0]
    fn=om.MFnMesh(path);values=fn.getPoints();values[0].y+=.3;fn.setPoints(values)
    checks['direct_api_edit']=update()[0]
    cmds.setAttr(shape+'.displaySmoothMesh',2)
    try:stream.update();checks['smooth_switch_requires_rebuild']=False
    except RuntimeError:checks['smooth_switch_requires_rebuild']=True
    stream.close();stream=SceneStream([shape]);checks['smooth_initial_geometry']=update(True)[0]
    cmds.hide(cube);rows=list(records(stream.update()))
    checks['hide_only_updates_visibility']=len(rows)==1 and rows[0]['flags']==16 and not rows[0]['visible']
    cmds.move(.3,0,0,cube+'.vtx[0]',relative=True);rows=list(records(stream.update()))
    checks['hidden_geometry_is_not_evaluated']=not rows and stream.dll.es_evaluations(stream.pointer)==0
    cmds.showHidden(cube);checks['reveal_reads_latest_deformation']=update()[0]
    stream.close();cmds.hide(cube);stream=SceneStream([shape]);checks['hidden_initial_uses_base']=update(True)[0]
    spec=exporter.mesh(path,{},binary=False)
    checks['hidden_export_matches_base_packet']=len(spec['points'])==8
    cmds.showHidden(cube)
    try:stream.update();checks['reveal_requests_smooth_topology']=False
    except RuntimeError:checks['reveal_requests_smooth_topology']=True
    stream.close();stream=SceneStream([shape]);update(True)
    bend,handle=cmds.nonLinear(cube,type='bend')
    stream.close();stream=SceneStream([shape]);update(True)
    for frame,value in ((1,0),(2,25),(3,50)):
        cmds.setKeyframe(bend,attribute='curvature',time=frame,value=value)
    for mode in ('off','serial','parallel'):
        cmds.evaluationManager(mode=mode)
        for frame in (1,2,3,2,1):
            cmds.currentTime(frame)
            checks['deformer_%s_frame_%s_%s'%(mode,frame,len(checks))]=update()[0]
    stream.close();stream=None
    cmds.setAttr(bend+'.curvature',0)
    checks['closed_cache_removes_callbacks']=True
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2))
    assert all(checks.values()),checks
finally:
    if stream:stream.close()
    maya.standalone.uninitialize();profile.cleanup()
