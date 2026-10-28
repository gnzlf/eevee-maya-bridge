"""Mayapy: native HDRI creation, shared-image isolation and Undo."""
import os,sys,tempfile,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
profile=tempfile.TemporaryDirectory(prefix='Eevee-hdri-controls-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1';sys.path.insert(0,str(root/'scripts'))
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds
from eevee_maya import hdri,exporter
try:
    cmds.undoInfo(state=True)
    checks={'no_arnold_no_domes':hdri.domes()==[]}
    source=Path(profile.name)/'environment.hdr';source.write_bytes(b'synthetic descriptor; image decoding is tested by the GUI fixture')
    shape=hdri.create(str(source));image,attribute=hdri.image_connection(shape)
    checks['native_dome_and_image_created']=shape in hdri.domes() and cmds.nodeType(image)=='file' and Path(cmds.getAttr(image+'.'+attribute))==source
    checks['native_color_rule_applied']=cmds.getAttr(image+'.colorSpace')==cmds.colorManagementFileRules(evaluate=str(source))
    original=cmds.shadingNode('aiSkyDomeLight',asLight=True)
    other=cmds.listRelatives(original,shapes=True,fullPath=True)[0]
    cmds.connectAttr(image+'.outColor',other+'.color')
    replacement=Path(profile.name)/'replacement.exr';replacement.write_bytes(b'synthetic descriptor')
    separate=hdri.load_image(shape,str(replacement))
    checks['shared_image_is_not_changed']=separate!=image and Path(cmds.getAttr(image+'.fileTextureName'))==source and hdri.image_connection(other)[0]==image
    checks['only_requested_dome_changes_image']=hdri.image_connection(shape)[0]==separate and Path(cmds.getAttr(separate+'.fileTextureName'))==replacement
    cmds.undo()
    checks['replace_image_is_one_undo_step']=hdri.image_connection(shape)[0]==image and not cmds.objExists(separate)
    cmds.disconnectAttr(image+'.outColor',other+'.color')
    material=cmds.shadingNode('standardSurface',asShader=True)
    cmds.connectAttr(image+'.outAlpha',material+'.opacityR')
    alpha_separate=hdri.load_image(shape,str(replacement))
    checks['shared_alpha_connection_is_not_changed']=alpha_separate!=image and Path(cmds.getAttr(image+'.fileTextureName'))==source and cmds.connectionInfo(material+'.opacityR',sourceFromDestination=True)==image+'.outAlpha'
    before=set(cmds.ls())
    try:hdri.create(str(source)+'.absent')
    except ValueError:pass
    checks['missing_image_creates_no_nodes']=set(cmds.ls())==before
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values()),checks
finally:maya.standalone.uninitialize();profile.cleanup()
