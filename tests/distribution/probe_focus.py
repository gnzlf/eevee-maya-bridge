"""Validate autofocus on evaluated surfaces, selected components, units and camera rigs."""
import json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
profile=tempfile.TemporaryDirectory(prefix='Eevee-focus-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
import maya.api.OpenMaya as om
from eevee_maya import focus
checks={}
try:
    camera,shape=cmds.camera();cmds.setAttr(shape+'.focalLength',50)
    head=cmds.polyCube(width=20,height=20,depth=40)[0];cmds.setAttr(head+'.translateZ',-200)
    path=focus.camera_path(camera)
    point=focus.selection_point(path,[head]);checks['front_surface_not_bbox_center']=abs(focus.depth(path,point)-180)<1e-4
    cmds.setAttr(camera+'.scale',64,64,64,type='double3');path=focus.camera_path(camera)
    checks['scaled_camera_same_world_depth']=abs(focus.depth(path,focus.selection_point(path,[head]))-180)<1e-4
    cmds.currentUnit(linear='m');path=focus.camera_path(camera)
    checks['working_unit_meters']=abs(focus.depth(path,focus.selection_point(path,[head]))-180)<1e-4
    component=head+'.vtx[0]';p=cmds.pointPosition(component,world=True);expected=-p[2]*100
    checks['selected_component_exact_depth']=abs(focus.depth(path,focus.selection_point(path,[component]))-expected)<1e-4
    cmds.currentUnit(linear='cm')
    ctrl=cmds.circle(normal=(0,0,1),radius=2)[0];cmds.setAttr(ctrl+'.translateZ',-200)
    checks['facial_control_hits_visible_mesh']=abs(focus.depth(path,focus.selection_point(path,[ctrl]))-180)<1e-4
    cmds.setAttr(head+'.visibility',False)
    checks['hidden_mesh_not_picked']=focus.ray_hit(om.MPoint(0,0,0),om.MVector(0,0,-1),focus.visible_meshes()) is None
    cmds.setAttr(head+'.visibility',True);cmds.setAttr(head+'.translateZ',-250)
    checks['evaluated_transform_updates_hit']=abs(focus.depth(path,focus.selection_point(path,[head]))-230)<1e-4
    cmds.setAttr(shape+'.orthographic',True);cmds.setAttr(head+'.translateX',30)
    checks['orthographic_focus_through_selection']=abs(focus.depth(path,focus.selection_point(path,[head]))-230)<1e-4
    cmds.setAttr(shape+'.orthographic',False);cmds.setAttr(head+'.visibility',False)
    sphere=cmds.polySphere(radius=20,subdivisionsX=256,subdivisionsY=128)[0]
    cmds.setAttr(sphere+'.translate',50,0,-200,type='double3')
    expected=200-20*200/(200**2+50**2)**.5
    checks['off_axis_perspective_surface']=abs(focus.depth(path,focus.selection_point(path,[sphere]))-expected)<.01
    skinned=cmds.polyCube(width=20,height=20,depth=40)[0];cmds.setAttr(skinned+'.translateZ',-300)
    cmds.select(clear=True);joint=cmds.joint();cmds.skinCluster(joint,skinned,toSelectedBones=True)
    before=focus.depth(path,focus.selection_point(path,[skinned]))
    cmds.setAttr(joint+'.translateZ',20)
    checks['skin_deformation_updates_surface']=abs(before-280)<.001 and abs(focus.depth(path,focus.selection_point(path,[skinned]))-260)<.001
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values())
finally:maya.standalone.uninitialize();profile.cleanup()
