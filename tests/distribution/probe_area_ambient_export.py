"""Mayapy: native lights must work with or without mtoa loaded."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
profile=tempfile.TemporaryDirectory(prefix='Eevee-light-export-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
sys.path.insert(0,str(ROOT/'scripts'))
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds
import maya.api.OpenMaya as om
from eevee_maya import exporter,maya_lights
from eevee_maya.light_links import LightLinks
from eevee_maya.changes import SceneChanges
links=changes=None
try:
    cube=cmds.polyCube()[0];shape=cmds.listRelatives(cube,shapes=True,fullPath=True)[0]
    native={kind:cmds.shadingNode(kind,asLight=True) for kind in ('pointLight','directionalLight','spotLight','areaLight','ambientLight')}
    specs=exporter.lights();checks={}
    checks['all_native_lights_export_without_arnold']=set(s['kind'] for s in specs)==set(native)
    checks['unregistered_arnold_type_is_not_queried']='aiAreaLight' not in maya_lights.types()
    cmds.loadPlugin('mtoa',quiet=True)
    arnold=cmds.shadingNode('aiAreaLight',asLight=True)
    arnold_shape=cmds.listRelatives(arnold,shapes=True,fullPath=True)[0]
    cmds.setAttr(arnold+'.scale',3,2,1,type='double3')
    cmds.setAttr(arnold_shape+'.aiExposure',2);cmds.setAttr(arnold_shape+'.normalize',False)
    spec=next(s for s in exporter.lights() if s['kind']=='aiAreaLight')
    checks['arnold_area_uses_its_native_parameters']=spec['name']==arnold_shape and spec['exposure']==2 and not spec['normalize'] and spec['decay']==2 and spec['size_x']==6 and spec['size_y']==4
    cmds.select(arnold);checks['arnold_transform_selection_finds_shape']=arnold_shape in maya_lights.selected()
    links=LightLinks();checks['arnold_native_light_links']=links.read([shape],[arnold_shape])[arnold_shape]['receivers']==[shape]
    cmds.lightlink(light=arnold_shape,object=cube,b=True)
    checks['arnold_light_link_edits_invalidate']=links.read([shape],[arnold_shape])[arnold_shape]['receivers']==[]
    changes=SceneChanges();changes.refresh_callbacks();changes.structural=changes.dirty=False
    cmds.setAttr(arnold+'.translateX',1)
    checks['arnold_light_motion_does_not_reexport_geometry']=not changes.dirty and not changes.structural
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2))
    assert all(checks.values()),checks
finally:
    if links:links.close()
    if changes:changes.close()
    maya.standalone.uninitialize();profile.cleanup()
