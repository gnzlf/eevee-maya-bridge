"""Run with Blender --background --python to verify cached atmosphere range math."""
import json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'blender'));sys.path.insert(0,str(root/'scripts'))
import worker
from scene_sync import world_bounds,position_atmosphere,update_effects
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
cam=bpy.data.objects.new('ProbeCamera',bpy.data.cameras.new('ProbeCamera'));bpy.context.scene.collection.objects.link(cam);bpy.context.scene.camera=cam
objects=[]
for x,y,z in ((0,0,-100),(10,5,-350),(-20,-5,-250)):
    bpy.ops.mesh.primitive_cube_add(size=4);obj=bpy.context.object;obj.matrix_world=worker.CONVERSION @ Matrix.Translation((x,y,z));objects.append(obj)
request={'camera':{'matrix':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'near':.1,'far':1000,'orthographic':False,'fov_x':.8,'ortho_width':20},'effects':{'fog':True,'fog_distance':20,'fog_auto_range':True},'width':960,'height':540}
update_effects(request);checks={}
for angle in (0,.3,-.5):
    cam.matrix_world=worker.CONVERSION @ Matrix.Rotation(angle,4,'Y')
    view=cam.matrix_world.inverted();expected=20
    for obj in objects:
        matrix=view @ obj.matrix_world
        z=max(-(matrix @ Vector(corner)).z for corner in obj.bound_box)
        if z>.1:expected=max(expected,min(1000,z*1.05))
    points=world_bounds(objects);position_atmosphere(request,bounds=points)
    actual=bpy.context.scene.eevee.volumetric_end
    checks['matches_scalar_reference_'+str(angle)]=abs(actual-expected)<.001
    volume=bpy.data.objects['EeveeAtmosphereVolume'];before=volume.matrix_world.copy()
    position_atmosphere(request,objects=objects)
    checks['cached_and_uncached_same_'+str(angle)]=all(abs(a-b)<.001 for a,b in zip(sum((list(row) for row in before),[]),sum((list(row) for row in volume.matrix_world),[])))
print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values())
