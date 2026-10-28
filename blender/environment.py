"""Arnold lat-long domes as Eevee world lighting and material reflections."""
import json
import math
import bpy
from mathutils import Matrix
from eevee_maya import color_management

_signature = None
_topology = None
_rebuilds = 0
_state = {}


def sync_environment(mode, lights=(), selected=(), shadows=True):
    global _signature, _state, _topology, _rebuilds
    world = bpy.context.scene.world
    world.use_nodes = True
    tree = world.node_tree
    domes = [s for s in lights if s['kind'] == 'aiSkyDomeLight' and
             (mode == 'all' or mode in ('active', 'selected') and s['name'] in selected)]
    # Local lights, camera navigation and deformation do not invalidate the IBL.
    signature = (world.as_pointer(), mode, shadows, json.dumps(domes, sort_keys=True))
    if signature == _signature and tree.nodes.get('EeveeBackgroundMix'):
        return _state
    topology = (world.as_pointer(), [(s['name'], s.get('texture'), s.get('warning'),
                                    s.get('format', 2), s.get('camera', 1) > 0) for s in domes])
    if topology != _topology or not tree.nodes.get('EeveeBackgroundMix'):
        for n in list(tree.nodes):
            if n.name.startswith('EeveeHDRI'):
                tree.nodes.remove(n)
        _rebuilds += 1

    def node(kind, name):
        result = tree.nodes.get(name) or tree.nodes.new(kind)
        result.name = name
        return result

    def link(output, input_):
        if not input_.is_linked or input_.links[0].from_socket != output:
            tree.links.new(output, input_)

    def value(socket, new):
        old = tuple(socket.default_value) if isinstance(new, tuple) else socket.default_value
        if old != new:
            socket.default_value = new

    background = tree.nodes.get('Background') or node('ShaderNodeBackground', 'Background')
    value(background.inputs[0], (.12, .12, .12, 1))
    value(background.inputs[1], .5)
    ambient = node('ShaderNodeBackground', 'EeveeAmbientLighting')
    value(ambient.inputs[0], (1, 1, 1, 1))
    value(ambient.inputs[1], 1 if mode == 'flat' else 0)
    path = node('ShaderNodeLightPath', 'EeveeBackgroundOnly')
    mix = node('ShaderNodeMixShader', 'EeveeBackgroundMix')
    lighting = ambient.outputs[0]
    camera = None
    sources, warnings = [], []
    resolutions = []
    additions = 0

    def add(a, b):
        nonlocal additions
        if a is None:
            return b
        n = node('ShaderNodeAddShader', 'EeveeHDRIAdd' + str(additions))
        additions += 1
        link(a, n.inputs[0]); link(b, n.inputs[1])
        return n.outputs[0]

    for i, spec in enumerate(domes):
        warning = spec.get('warning')
        if spec.get('format', 2) != 2:
            warning = 'HDRI: solo se admite el formato lat-long'
        if warning:
            warnings.append(spec['name'] + ': ' + warning)
            continue
        label = 'EeveeHDRI' + str(i)
        shader = node('ShaderNodeBackground', label + 'Lighting')
        strength = max(0, spec.get('intensity', 1)) * 2 ** max(-30, min(30, spec.get('exposure', 0)))
        value(shader.inputs['Strength'], strength)
        value(shader.inputs['Color'], (*spec.get('color', (1, 1, 1)), 1))
        texture = spec.get('texture')
        if texture:
            image = node('ShaderNodeTexEnvironment', label + 'Texture')
            try:
                if image.image is None:
                    image.image = bpy.data.images.load(texture['path'], check_existing=True)
                space = color_management.image_space(texture.get('color_space', 'sRGB'))
                if image.image.colorspace_settings.name != space:
                    image.image.colorspace_settings.name = space
            except (RuntimeError, TypeError) as error:
                warnings.append(spec['name'] + ': ' + str(error))
                tree.nodes.remove(shader)
                continue
            coordinates = node('ShaderNodeTexCoord', label + 'Coordinates')
            # Direction only: dome translation and scale must not move the sky.
            from worker import CONVERSION, transform
            rotation = transform(spec['matrix']).to_quaternion().to_matrix()
            # Arnold's lat-long seam is local -Z; Blender's seam is local -X.
            # Verified against a linear UV-gradient rendered by Arnold CPU.
            mapping = Matrix.Rotation(math.pi/2, 3, 'Z') @ CONVERSION.to_3x3() @ rotation.inverted()
            combine = node('ShaderNodeCombineXYZ', label + 'Direction')
            for axis, row in enumerate(mapping):
                dot = node('ShaderNodeVectorMath', label + 'Axis' + str(axis))
                dot.operation = 'DOT_PRODUCT'
                value(dot.inputs[1], tuple(row))
                link(coordinates.outputs['Generated'], dot.inputs[0])
                link(dot.outputs['Value'], combine.inputs[axis])
            link(combine.outputs[0], image.inputs[0])
            link(image.outputs['Color'], shader.inputs['Color'])
        lighting = add(lighting, shader.outputs[0])
        visibility = max(0, spec.get('camera', 1))
        if visibility:
            visible = node('ShaderNodeBackground', label + 'Camera')
            value(visible.inputs['Strength'], strength * visibility)
            value(visible.inputs['Color'], tuple(shader.inputs['Color'].default_value))
            if texture:
                link(image.outputs['Color'], visible.inputs['Color'])
            camera = add(camera, visible.outputs[0])
        if spec.get('diffuse', 1) != 1 or spec.get('specular', 1) != 1:
            warnings.append(spec['name'] + ': pesos Diffuse/Specular independientes no disponibles para World')
        sources.append({'name': spec['name'], 'texture': texture['path'] if texture else None,
                        'strength': strength, 'camera': visibility})
        resolutions.append(max(128, min(4096, spec.get('resolution', 1000))))
    link(path.outputs['Is Camera Ray'], mix.inputs[0])
    link(lighting, mix.inputs[1])
    link(camera or background.outputs[0], mix.inputs[2])
    output = next(n for n in tree.nodes if n.type == 'OUTPUT_WORLD')
    link(mix.outputs[0], output.inputs['Surface'])
    # Keep the HDR range in the world probe; do not synthesize a directional sun.
    if world.sun_threshold != 0: world.sun_threshold = 0
    if world.use_sun_shadow != bool(shadows): world.use_sun_shadow = bool(shadows)
    resolution = str(2 ** math.ceil(math.log2(max(resolutions, default=1000))))
    if world.probe_resolution != resolution: world.probe_resolution = resolution
    _state = {'sources': sources, 'warnings': warnings, 'probe_resolution': world.probe_resolution,
              'graph_rebuilds': _rebuilds}
    _signature = signature
    _topology = topology
    return _state
