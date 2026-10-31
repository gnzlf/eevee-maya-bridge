"""Blender background: mixed receiver stability and compatibility transitions."""
import json,math,sys
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'scripts'),str(root/'blender')]
import worker
from scene_sync import SceneMirror

bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.world=bpy.data.worlds.new('FixtureWorld');scene.world.use_nodes=True
mirror=SceneMirror();checks={}
for name,z,kind in (('Classic',0,'lambert'),('Physical',-5,'aiStandardSurface')):
 bpy.ops.mesh.primitive_cube_add(size=1)
 obj=bpy.context.object;obj.name=name;obj['maya_path']=name
 source=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,z,1];obj.matrix_world=worker.transform(source)
 mat=bpy.data.materials.new(name);mat['eevee_maya_material_kind']=kind;obj.data.materials.append(mat)
 mirror.objects[name]=obj;mirror.original_materials[name]=[mat]
scene.view_layers[0].update()
matrix=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,5,1]
base={'name':'FixtureArea','kind':'areaLight','matrix':matrix,'intensity':2,'exposure':0,'color':[1,1,1],
 'decay':0,'decay_reference':5,'normalize':True,'size_x':2,'size_y':2,'volume':True,'volume_factor':1,
 'intensity_mode':'viewport2','receivers':['Classic','Physical']}
request={'lights':[base],'native':{'displayLights':'all','shadows':False,'useDefaultMaterial':False},'effects':{},'camera':{'matrix':matrix}}
mirror.sync_lights(request);obj=bpy.data.objects['FixtureArea']
first=mirror.light_specs['FixtureArea'];gain=first['receiver_gain']
checks['mixed_gain_is_between_conventions']=abs(gain-(1+math.pi)*.5)<1e-9
checks['area_uses_calibrated_power']=abs(obj.data.energy-2*math.pi*gain)<1e-4
checks['calibrated_area_has_finite_receiver_range']=obj.data.use_custom_distance
old=worker.light_photometry.energy(base,legacy=True)
checks['volume_preserves_legacy_power']=abs(obj.data.energy*obj.data.volume_factor-old)<.001
# Swap the receiver order along the beam; their material mixture is unchanged.
a,b=mirror.objects['Classic'],mirror.objects['Physical'];a.matrix_world,b.matrix_world=b.matrix_world.copy(),a.matrix_world.copy()
scene.view_layers[0].update();mirror.geometry_revision+=1;mirror.light_bounds=None
mirror.sync_lights(request)
checks['receiver_order_does_not_jump_exposure']=mirror.light_specs['FixtureArea']['receiver_gain']==gain
request['lights']=[dict(base,intensity_mode='legacy')];mirror.sync_lights(request)
checks['legacy_power_restored']=abs(obj.data.energy-old)<.001 and obj.data.volume_factor==1
checks['legacy_area_restores_automatic_range']=not obj.data.use_custom_distance
sun=dict(base,name='FixtureSun',kind='directionalLight')
request['lights']=[sun];mirror.light_bounds=None;mirror.sync_lights(request)
sun_obj=bpy.data.objects['FixtureSun']
checks['sun_calibration_does_not_calculate_receiver_bounds']=mirror.light_bounds is None
checks['sun_uses_stable_material_convention']=abs(sun_obj.data.energy-2*gain)<.00001
print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values()),checks
