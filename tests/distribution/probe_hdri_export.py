"""Mayapy: discover Arnold domes without requiring mtoa for ordinary lights."""
import json
import os
from pathlib import Path
import sys
import tempfile
profile=tempfile.TemporaryDirectory(prefix='Eevee-hdri-export-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds
from eevee_maya import exporter,maya_lights
from eevee_maya.changes import SceneChanges
changes=None
try:
    checks={'missing_mtoa_is_safe':'aiSkyDomeLight' not in maya_lights.types()}
    cmds.loadPlugin('mtoa',quiet=True)
    parent=cmds.shadingNode('aiSkyDomeLight',asLight=True)
    shape=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
    cmds.setAttr(shape+'.intensity',.5);cmds.setAttr(shape+'.exposure',3);cmds.setAttr(shape+'.camera',0)
    spec=exporter.lights()[0]
    checks['dome_parameters_exported']=spec['kind']=='aiSkyDomeLight' and spec['intensity']==.5 and spec['exposure']==3 and spec['camera']==0 and spec['format']==2
    cmds.select(parent);checks['native_selected_dome']=shape in maya_lights.selected()
    for kind,attribute in (('file','fileTextureName'),('aiImage','filename')):
        image=cmds.shadingNode(kind,asTexture=True)
        path=Path(profile.name)/(kind+'.exr');path.write_bytes(b'test source descriptor')
        cmds.setAttr(image+'.'+attribute,str(path),type='string');cmds.setAttr(image+'.colorSpace','Raw',type='string')
        cmds.connectAttr(image+'.outColor',shape+'.color',force=True)
        spec=exporter.lights()[0]
        checks[kind+'_source_descriptor']=Path(spec['texture']['path'])==path and spec['texture']['color_space']=='Raw' and spec['color']==[1,1,1]
        cmds.setAttr(image+'.'+attribute,str(path)+'.missing',type='string')
        spec=exporter.lights()[0];checks[kind+'_missing_file_reported']=bool(spec['warning']) and spec['texture'] is None
    changes=SceneChanges();changes.refresh_callbacks();changes.dirty=changes.structural=False
    cmds.setAttr(parent+'.rotateY',35)
    checks['rotation_keeps_geometry_alive']=not changes.dirty and not changes.structural
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values()),checks
finally:
    if changes:changes.close()
    maya.standalone.uninitialize();profile.cleanup()
