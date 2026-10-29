"""Real Maya UV sampling, cache invalidation, channel export, no scene edits."""
import json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
profile=tempfile.TemporaryDirectory(prefix='Eevee-texture-regression-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
sys.path.insert(0,str(ROOT/'scripts'))
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds
from eevee_maya import texture_bake,exporter,color_management
checks={}
try:
 cmds.undoInfo(state=True)
 ramp=cmds.shadingNode('ramp',asTexture=True)
 place=cmds.shadingNode('place2dTexture',asUtility=True)
 cmds.connectAttr(place+'.outUV',ramp+'.uvCoord');cmds.connectAttr(place+'.outUvFilterSize',ramp+'.uvFilterSize')
 for index in cmds.getAttr(ramp+'.colorEntryList',multiIndices=True) or []:
  if index>1:cmds.removeMultiInstance(ramp+'.colorEntryList[%d]'%index,b=True)
 cmds.setAttr(ramp+'.colorEntryList[0].position',0);cmds.setAttr(ramp+'.colorEntryList[1].position',1)
 cmds.setAttr(ramp+'.colorEntryList[0].color',.05,.2,.6,type='double3')
 cmds.setAttr(ramp+'.colorEntryList[1].color',3,.8,.15,type='double3')
 layers=cmds.shadingNode('layeredTexture',asTexture=True)
 cmds.connectAttr(ramp+'.outColor',layers+'.inputs[0].color')
 cmds.setAttr(layers+'.inputs[1].color',.3,.1,.05,type='double3');cmds.setAttr(layers+'.inputs[0].alpha',.5)
 cmds.setAttr(layers+'.inputs[0].blendMode',1)
 shader=cmds.shadingNode('standardSurface',asShader=True);cmds.connectAttr(layers+'.outColor',shader+'.baseColor')
 bump=cmds.shadingNode('bump2d',asUtility=True);noise=cmds.shadingNode('noise',asTexture=True)
 cmds.connectAttr(noise+'.outAlpha',bump+'.bumpValue');cmds.connectAttr(bump+'.outNormal',shader+'.normalCamera');cmds.setAttr(bump+'.bumpDepth',.2)
 cmds.connectAttr(place+'.outUV',noise+'.uvCoord');cmds.connectAttr(place+'.outUvFilterSize',noise+'.uvFilterSize')
 before=sorted(cmds.ls());modified=cmds.file(query=True,modified=True);undo=cmds.undoInfo(query=True,undoName=True);selection=cmds.ls(selection=True)
 first=texture_bake.bake(cmds,layers+'.outColor',64);count=texture_bake._bakes
 import maya.OpenMaya as om
 import maya.OpenMayaRender as render
 positions=[(5,7),(32,12),(40,49)]
 u=om.MFloatArray();v=om.MFloatArray();sizes=om.MFloatArray()
 for x,y in positions:u.append((x+.5)/64);v.append(1-(y+.5)/64);sizes.append(1/64)
 colors=om.MFloatVectorArray();trans=om.MFloatVectorArray()
 render.MRenderUtil.sampleShadingNetwork(layers+'.outColor',len(positions),False,False,om.MFloatMatrix(),None,u,v,None,None,None,None,sizes,colors,trans)
 expected=[{'x':x,'y':y,'rgb':[colors[i].x,colors[i].y,colors[i].z]} for i,(x,y) in enumerate(positions)]
 second=texture_bake.bake(cmds,layers+'.outColor',64)
 checks['cached_without_resampling']=first==second and texture_bake._bakes==count
 checks['no_scene_or_undo_changes']=sorted(cmds.ls())==before and cmds.file(query=True,modified=True)==modified and cmds.undoInfo(query=True,undoName=True)==undo and cmds.ls(selection=True)==selection
 cmds.setAttr(layers+'.inputs[0].alpha',.1)
 changed=texture_bake.bake(cmds,layers+'.outColor',64)
 checks['layer_parameter_invalidates_cache']=first['path']!=changed['path']
 cmds.setAttr(ramp+'.colorEntryList[1].color',1,2,3,type='double3')
 upstream=texture_bake.bake(cmds,layers+'.outColor',64)
 checks['upstream_parameter_invalidates_cache']=changed['path']!=upstream['path']
 normal=exporter.normal_texture(shader)
 checks['procedural_bump_preserved']=normal['texture']['baked'] and normal['strength']==1 and abs(normal['distance']-.2)<1e-6
 cmds.setAttr(bump+'.bumpDepth',-.2);checks['negative_bump_inverts']=exporter.normal_texture(shader)['invert']
 image=cmds.shadingNode('file',asTexture=True);cmds.setAttr(image+'.fileTextureName',first['path'],type='string')
 cmds.connectAttr(image+'.outColorR',shader+'.specularRoughness');checks['scalar_channel_preserved']=exporter.material(shader)['roughness_texture']['channel']=='outColorR'
 config=exporter.color_management();native=color_management.prepare_native(config,profile.name)
 checks['maya_config_resolved']=config['native_ocio'] and native is not None
 # Keep only generated fixtures for an independent Blender decode check.
 out=ROOT/'diagnostics/looks22';out.mkdir(exist_ok=True)
 import shutil
 for name,spec in [('layered',first),('changed',changed),('upstream',upstream),('noise',normal['texture'])]:
  shutil.copyfile(spec['path'],out/(name+'.exr'))
 if native:shutil.copyfile(native,out/'maya-color.ocio')
 (out/'texture-bake-result.json').write_text(json.dumps({'passed':all(checks.values()),'checks':checks,'color':config},indent=2))
 (out/'texture-reference.json').write_text(json.dumps(expected,indent=2))
 print(json.dumps(checks,indent=2));assert all(checks.values()),checks
finally:maya.standalone.uninitialize();profile.cleanup()
