"""Blender background fixture: compare optimized light edits with the prior link path."""
import copy
import json
from pathlib import Path
import statistics
import sys
import time
from unittest import mock

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'blender'))
import worker
import scene_sync

OUTPUT = ROOT / 'diagnostics' / 'light-link-update-probe'
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 320, 240, 100
scene.render.image_settings.file_format = 'PNG'
scene.eevee.taa_samples = 16
scene.eevee.use_taa_reprojection = False
scene.world = bpy.data.worlds.new('ProbeWorld')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0

camera = bpy.data.objects.new('ProbeCamera', bpy.data.cameras.new('ProbeCamera'))
scene.collection.objects.link(camera)
camera.location = (8, -10, 9)
camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera
headlight = bpy.data.objects.new('EeveeDefaultHeadlight', bpy.data.lights.new('EeveeDefaultHeadlight', 'SUN'))
headlight.data.energy = 2.5
scene.collection.objects.link(headlight)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, .5))
cube = bpy.context.object
cube['maya_path'] = 'cube'
bpy.ops.mesh.primitive_plane_add(size=12)
plane = bpy.context.object
plane['maya_path'] = 'ground'
material = bpy.data.materials.new('ProbeDiffuse')
material.use_nodes = True
shader = material.node_tree.nodes['Principled BSDF']
shader.inputs['Base Color'].default_value = (.7, .7, .7, 1)
shader.inputs['Roughness'].default_value = .6
cube.data.materials.append(material)
plane.data.materials.append(material)
mirror = scene_sync.SceneMirror()
mirror.objects = {'cube': cube, 'ground': plane}
for index in range(398):
    obj = bpy.data.objects.new('BackgroundMesh%03d' % index, cube.data)
    obj.location = (50 + index % 20, 50 + index // 20, .5)
    obj['maya_path'] = obj.name
    scene.collection.objects.link(obj)
    mirror.objects[obj.name] = obj
names = list(mirror.objects)


def matrix_at(x):
    location = Vector((x, -3, 6))
    rotation = (Vector((0, 0, 0)) - location).to_track_quat('-Z', 'Y').to_matrix().to_4x4()
    rotation.translation = location
    source = (worker.CONVERSION.inverted() @ rotation).transposed()
    return [value for row in source for value in row]


base = {'name': 'ProbeSpot', 'kind': 'spotLight', 'color': [1, 1, 1], 'intensity': 600,
        'exposure': 0, 'decay': 2, 'decay_reference': 5, 'diffuse': True, 'specular': True,
        'shadows': True, 'volume': True, 'volume_factor': 1, 'matrix': matrix_at(0),
        'cone_angle': 1.4, 'penumbra': .1, 'dropoff': 4,
        'receivers': names, 'shadow_blockers': names}


def request(spec, mode='all', selected=None):
    return {'lights': [spec], 'native': {'displayLights': mode, 'shadows': True,
                                        'selected_lights': selected or []}}


def previous_visibility(obj, visible):
    obj.hide_viewport = not visible
    obj.hide_render = not visible


def pixels(label):
    path = OUTPUT / (label + '.png')
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    bpy.data.images.remove(image)
    return values


checks = {}
comparisons = []
rendered = {}
specs = [copy.deepcopy(base) for _ in range(12)]
specs[1].update(matrix=matrix_at(2), intensity=900)
specs[2]['receivers'] = ['ground']
specs[3]['receivers'] = []
specs[4]['shadow_blockers'] = []
specs[5]['dropoff'] = 0
specs[6]['dropoff'] = 4
labels = ['initial', 'move_and_intensity', 'receiver_subset', 'no_receivers',
          'no_shadow_blockers', 'remove_helpers', 'recreate_helpers', 'selected_source',
          'selected_none', 'native_default', 'native_flat', 'native_none']
modes = {'selected_source': ('active', ['ProbeSpot']), 'selected_none': ('active', []),
         'native_default': ('default', []), 'native_flat': ('flat', []), 'native_none': ('none', [])}
original = mirror.sync_light_links
for label, spec in zip(labels, specs):
    current = request(spec, *modes.get(label, ('all', [])))
    with mock.patch.object(mirror, 'sync_light_links', wraps=original) as calls:
        mirror.sync_lights(current)
        optimized_calls = calls.call_count
    if label in modes:
        source_lights = [obj for obj in scene.objects if obj.type == 'LIGHT' and 'maya_path' in obj]
        checks[label + '_correct_light_visibility'] = all(
            obj.hide_viewport == (label != 'selected_source')
            and obj.hide_render == (label != 'selected_source') for obj in source_lights)
        checks[label + '_default_headlight_only_in_default_mode'] = (
            headlight.hide_viewport == (label != 'native_default')
            and headlight.hide_render == (label != 'native_default') and not headlight.data.use_shadow)
    optimized = pixels(label + '-optimized')
    rendered[label] = optimized
    mirror.light_signature = None
    # Only bypass the new equality check. This replays the former unconditional
    # link assignments with identical light values, geometry and render quality.
    with mock.patch.object(scene_sync, 'same_light_links', return_value=False), \
            mock.patch.object(scene_sync, 'set_light_visibility', side_effect=previous_visibility):
        mirror.sync_lights(copy.deepcopy(current))
    reference = pixels(label + '-reference')
    difference = float(np.max(np.abs(optimized - reference)))
    comparisons.append({'case': label, 'max_pixel_difference': difference,
                        'optimized_link_updates': optimized_calls})
    checks[label + '_same_image_as_reference'] = difference <= 1 / 255 + 1e-6
    if label == 'move_and_intensity' or label in modes:
        checks[label + '_skips_unchanged_link_assignments'] = optimized_calls == 0
    else:
        checks[label + '_initializes_or_invalidates_links'] = optimized_calls > 0
foreground = rendered['initial'].reshape(240, 320, 4)[20:120, 80:240, :3]
checks['fixture_foreground_is_actually_lit'] = float(foreground.mean()) > .03
checks['receiver_edits_change_the_render'] = float(np.max(np.abs(rendered['initial'] - rendered['no_receivers']))) > .05
checks['shadow_link_edits_change_the_render'] = float(np.max(np.abs(rendered['initial'] - rendered['no_shadow_blockers']))) > .01

# Measure only sync_lights, not copying, rendering, rig evaluation or playback.
timings = {}
for mode in ('reference', 'optimized'):
    samples = []
    for index in range(60):
        spec = copy.deepcopy(base)
        spec['intensity'] += index / 100
        if mode == 'reference':
            with mock.patch.object(scene_sync, 'same_light_links', return_value=False), \
                    mock.patch.object(scene_sync, 'set_light_visibility', side_effect=previous_visibility):
                started = time.perf_counter()
                mirror.sync_lights(request(spec))
                elapsed = (time.perf_counter() - started) * 1000
        else:
            started = time.perf_counter()
            mirror.sync_lights(request(spec))
            elapsed = (time.perf_counter() - started) * 1000
        if index >= 10:
            samples.append(elapsed)
    timings[mode] = {'median_ms': statistics.median(samples), 'samples': len(samples)}

result = {'passed': all(checks.values()), 'checks': checks, 'images': comparisons,
          'sync_only_timings': timings, 'meshes': len(names),
          'note': 'Microbenchmark of light synchronization only; not a viewport FPS measurement.'}
(OUTPUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
if not result['passed']:
    raise AssertionError('Light-link update regression')
