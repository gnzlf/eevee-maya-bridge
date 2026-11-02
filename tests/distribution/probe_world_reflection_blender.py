"""Run inside Blender: does a mirror reflect the HDRI built by environment.sync_environment?

blender -b --factory-startup --python probe_world_reflection_blender.py -- <hdri> <out.json>
Renders a black mirror sphere (IOR 1.52, roughness 0) and a Blinn-like sphere
with the bridge's world graph, background hidden from camera vs. visible.
"""
import json,sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'blender'),str(ROOT/'scripts')]
argv=sys.argv[sys.argv.index('--')+1:];hdri,out=argv[0],Path(argv[1])
import environment

scene=bpy.context.scene
for o in list(bpy.data.objects):bpy.data.objects.remove(o)
scene.render.engine='BLENDER_EEVEE';scene.eevee.taa_samples=4
scene.render.resolution_x=640;scene.render.resolution_y=320;scene.render.image_settings.file_format='PNG'
scene.view_settings.view_transform='Standard'
if scene.world is None:scene.world=bpy.data.worlds.new('World')
bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,location=(-1.2,0,0));mirror=bpy.context.object
bpy.ops.object.shade_smooth()
m=bpy.data.materials.new('mirror');m.use_nodes=True;p=m.node_tree.nodes['Principled BSDF']
p.inputs['Base Color'].default_value=(0,0,0,1);p.inputs['Roughness'].default_value=0;p.inputs['IOR'].default_value=1.52
mirror.data.materials.append(m)
bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,location=(1.2,0,0));chrome=bpy.context.object
bpy.ops.object.shade_smooth()
c=bpy.data.materials.new('chrome');c.use_nodes=True;q=c.node_tree.nodes['Principled BSDF']
q.inputs['Base Color'].default_value=(1,1,1,1);q.inputs['Metallic'].default_value=1;q.inputs['Roughness'].default_value=0
chrome.data.materials.append(c)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('cam'));scene.collection.objects.link(cam);scene.camera=cam
cam.location=(0,-8,0);cam.rotation_euler=(1.5708,0,0);cam.data.lens=50
results={}
for label,visible in (('hidden',0),('visible',1),('direct',1)):
    spec={'name':'dome','kind':'aiSkyDomeLight','intensity':1,'exposure':0,'color':(1,1,1),'camera':visible,
          'texture':{'path':hdri,'color_space':'Raw'},'matrix':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'format':2,'resolution':1000}
    state=environment.sync_environment('all',[spec],())
    tree=scene.world.node_tree;output=next(n for n in tree.nodes if n.type=='OUTPUT_WORLD')
    if label=='direct':
        # Bypass the Is Camera Ray mix: HDRI everywhere.
        tree.links.new(tree.nodes['EeveeHDRI0Lighting'].outputs[0],output.inputs['Surface'])
    path=out.with_name(out.stem+'_'+label+'.png');scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    img=bpy.data.images.load(str(path));px=list(img.pixels);w,h=img.size
    def at(x,y):i=(y*w+x)*4;return [round(v,4) for v in px[i:i+3]]
    # sphere centres in image space
    results[label]={'mirror_center':at(int(w*.5-w*.15*1.0),h//2),'chrome_center':at(int(w*.5+w*.15),h//2),'corner':at(5,5),'state':state}
out.write_text(json.dumps(results,indent=2,default=str));print(json.dumps(results,default=str))
